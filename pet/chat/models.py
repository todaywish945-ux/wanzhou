from __future__ import annotations

import importlib
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

def utc_now(): return datetime.now(timezone.utc).isoformat()

def _safe_float(v, default, lo=None, hi=None):
    """容错数值解析：配置被手改/损坏时回退默认值而不是抛异常。"""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if lo is not None: x = max(lo, x)
    if hi is not None: x = min(hi, x)
    return x

def _safe_int(v, default, lo=None, hi=None):
    try:
        x = int(float(v))
    except (TypeError, ValueError):
        return default
    if lo is not None: x = max(lo, x)
    if hi is not None: x = min(hi, x)
    return x

THINKING_MODES=('auto','enabled','disabled')
REASONING_EFFORTS=('low','high','max')
WEB_SEARCH_ENGINES=('baidu','duckduckgo','bocha','tavily')
# 需要 API Key 的搜索引擎（其余为免 Key 的网页抓取）
WEB_SEARCH_KEYED_ENGINES=('bocha','tavily')

#: 零宽字符：复制网页文字时容易把 BOM / 零宽空格一起带进 Key，肉眼不可见
#: 但会让请求头编码炸掉（2026-11-28 实测：'latin-1' codec can't encode ...）。
_ZERO_WIDTH_CHARS = '\ufeff\u2060\u200b\u200c\u200d\u200e\u200f'

def sanitize_api_key(raw: str) -> str:
    """去掉粘贴进来的首尾空白与零宽字符；其余内容原样保留。"""
    key = str(raw or '')
    for ch in _ZERO_WIDTH_CHARS:
        key = key.replace(ch, '')
    return key.strip()

def api_key_problem(key: str) -> str:
    """非空 API Key 的结构问题，返回中文提示；'' 表示可以直接使用。

    各家 Key（sk- 开头 / UUID / 纯字母数字）都是可打印 ASCII；只要出现
    非 ASCII 字符，就必然是复制时带上了页面文字、中文标点或全角空格——
    这种 Key 发出去会在 http.client 编码 Authorization 头时报
    ``'latin-1' codec can't encode ...``（英文报错，用户看不懂），
    所以在保存与发送两侧都拦下，给一句人话。
    """
    if not key:
        return ''
    bad = [ch for ch in key if not (32 <= ord(ch) <= 126)]
    if bad:
        return ('密钥里混入了非英文字符（常见于整段复制了页面文字、带上了中文标注或全角空格）。'
                '请回到服务商控制台，只复制密钥本身（通常是一串英文数字，如 sk- 开头）再重新粘贴。')
    return ''

def endpoint_url_problem(url: str) -> str:
    """API 地址的问题提示；'' 表示可用（空串由调用方决定语义）。"""
    url = str(url or '').strip()
    if not url:
        return ''
    if not (url.startswith('http://') or url.startswith('https://')):
        return 'API 地址需要以 http:// 或 https:// 开头。'
    bad = [ch for ch in url if ord(ch) > 127]
    if bad:
        return 'API 地址里混入了非英文字符，请重新粘贴服务商标注的接口地址本身。'
    return ''

def _choice(v, choices, default):
    v=str(v or '').strip().lower()
    return v if v in choices else default

@dataclass
class WebSearchSettings:
    """联网搜索（全局，所有 provider 共用）。DeepSeek 官方 API 无内置联网，
    由桌宠先调用搜索引擎、再把结果作为上下文交给模型。"""
    enabled: bool=False; engine: str='baidu'; api_key_ref: str='websearch/api'; api_key: str=''; max_results: int=5; fetch_pages: bool=True
    @classmethod
    def from_dict(cls,raw):
        raw=raw if isinstance(raw,dict) else {}
        return cls(bool(raw.get('enabled',False)),_choice(raw.get('engine','baidu'),WEB_SEARCH_ENGINES,'baidu'),str(raw.get('api_key_ref','websearch/api') or 'websearch/api'),str(raw.get('api_key','')),_safe_int(raw.get('max_results',5),5,lo=1,hi=10),bool(raw.get('fetch_pages',True)))
    def to_dict(self,include_secret=True):
        d=asdict(self)
        if not include_secret: d.pop('api_key',None)
        return d
    def resolve_api_key(self):
        return SecretStore().get(self.api_key_ref) or self.api_key

@dataclass
class ProviderConfig:
    provider_id: str
    name: str='智谱 GLM'; base_url: str='https://open.bigmodel.cn/api/paas/v4'; chat_path: str='/chat/completions'; model: str='glm-4.5-flash'; api_key_ref: str=''; api_key: str=''; timeout: float=60.0; temperature: float=0.7; max_tokens: int=2048; vision_model: str=''; vision_same_as_chat: bool=True; vision_base_url: str=''; vision_api_key_ref: str=''; vision_api_key: str=''; verify_ssl: bool=True
    # 深度思考：auto=不发送思考参数（沿用服务端默认；DeepSeek V4 默认开启思考）；enabled/disabled=显式开关
    thinking: str='auto'; reasoning_effort: str='high'
    # 运行时注入的联网搜索设置（来自 ChatSettings.web_search，不随 provider 落盘）
    web_search: Any=field(default=None, repr=False, compare=False)
    @classmethod
    def from_dict(cls,pid,raw):
        c = cls(str(pid), str(raw.get('name', pid)), str(raw.get('base_url', 'https://open.bigmodel.cn/api/paas/v4')), str(raw.get('chat_path', '/chat/completions')), str(raw.get('model', 'glm-4.5-flash')), str(raw.get('api_key_ref', f'provider/{pid}')), str(raw.get('api_key', '')), _safe_float(raw.get('timeout', 60), 60.0, lo=1.), _safe_float(raw.get('temperature', .7), 0.7, lo=0., hi=2.), _safe_int(raw.get('max_tokens', 2048), 2048, lo=1), verify_ssl=bool(raw.get('verify_ssl', True)))
        c.vision_model=str(raw.get('vision_model','')); c.vision_same_as_chat=bool(raw.get('vision_same_as_chat',True))
        c.vision_base_url=str(raw.get('vision_base_url','')); c.vision_api_key_ref=str(raw.get('vision_api_key_ref','')); c.vision_api_key=str(raw.get('vision_api_key',''))
        c.thinking=_choice(raw.get('thinking','auto'),THINKING_MODES,'auto'); c.reasoning_effort=_choice(raw.get('reasoning_effort','high'),REASONING_EFFORTS,'high')
        return c
    def to_dict(self,include_secret=True):
        d=asdict(self); d.pop('provider_id',None); d.pop('web_search',None)
        if not include_secret: d.pop('api_key',None); d.pop('vision_api_key',None)
        return d

#: 官方厂商预设（2026-11-28 定案：官方 API 地址固定，选厂商即带出 URL+模型默认值；
#: base_url/chat_path 按各官方文档口径，与 ProviderConfig 的拆分字段直接对应。
#: 中转站/本地模型不在表内——那些本来就要手填，走通用输入框）。
#: model 只是"出厂推荐值"，用户随时可改；不锁定。
PROVIDER_PRESETS: dict[str, dict] = {
    'zhipu': {
        'label': '智谱 GLM',
        'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'chat_path': '/chat/completions',
        'model': 'glm-4.5-flash',
        'models': ['glm-4.5-flash', 'glm-4.6', 'glm-4.5-air', 'glm-4-plus'],
        'key_hint': 'bigmodel.cn 控制台 → API Keys',
    },
    'siliconflow': {
        'label': '硅基流动 SiliconFlow',
        'base_url': 'https://api.siliconflow.cn/v1',
        'chat_path': '/chat/completions',
        'model': 'Qwen/Qwen2.5-7B-Instruct',
        'models': ['Qwen/Qwen2.5-7B-Instruct', 'deepseek-ai/DeepSeek-V3', 'THUDM/glm-4-9b-chat'],
        'key_hint': 'siliconflow.cn → API 密钥',
    },
    'deepseek': {
        'label': 'DeepSeek',
        'base_url': 'https://api.deepseek.com/v1',
        'chat_path': '/chat/completions',
        'model': 'deepseek-chat',
        'models': ['deepseek-chat', 'deepseek-reasoner'],
        'key_hint': 'platform.deepseek.com → API Keys',
    },
    'moonshot': {
        'label': '月之暗面 Kimi',
        'base_url': 'https://api.moonshot.cn/v1',
        'chat_path': '/chat/completions',
        'model': 'moonshot-v1-8k',
        'models': ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
        'key_hint': 'platform.moonshot.cn → API Key 管理',
    },
    'qwen': {
        'label': '阿里通义千问',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'chat_path': '/chat/completions',
        'model': 'qwen-plus',
        'models': ['qwen-plus', 'qwen-turbo', 'qwen-max'],
        'key_hint': '阿里云百炼控制台 → API-KEY',
    },
    'volcengine': {
        'label': '火山引擎（豆包）',
        'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'chat_path': '/chat/completions',
        'model': 'doubao-seed-1-6-flash',
        'models': ['doubao-seed-1-6-flash', 'doubao-seed-1-6', 'doubao-1-5-pro-32k'],
        'key_hint': '火山方舟控制台 → API Key 管理',
    },
    'local': {
        'label': '本地模型（Ollama 等）',
        'base_url': 'http://127.0.0.1:11434/v1',
        'chat_path': '/chat/completions',
        'model': 'qwen2.5:7b',
        'models': ['qwen2.5:7b', 'llama3.1:8b'],
        'key_hint': '本地服务无需 Key，留空即可',
    },
}

#: 智谱专有 Key 形态（id.secret：32 位十六进制 + 点 + 16 位字母数字）。
#: 别家（硅基流动/DeepSeek/Moonshot/OpenAI…）都是 sk- 前缀，彼此无法靠格式区分，
#: 所以嗅探只对「智谱格式」这一种高置信形态断言，其余一律不猜（宁可漏报）。
_ZHIPU_KEY_RE = re.compile(r'[0-9a-f]{32}\.[A-Za-z0-9]{16}')


def key_provider_mismatch(key: str, base_url: str) -> str:
    """保存前嗅探 Key 与服务商是否像一家。返回警告文案；像一家/拿不准返回空串。

    只断言双向高置信错位：智谱格式的 Key 配非智谱地址（2026-11-28 实机翻车：
    用户的智谱 Key 挂在 SiliconFlow 标签下，聊天 401「Token is invalid」）；
    以及智谱地址配明显非智谱的 Key。sk- 前缀各家通用，不做归属性断言。
    """
    key = str(key or '').strip()
    url = str(base_url or '')
    if not key or not url:
        return ''
    is_zhipu_key = bool(_ZHIPU_KEY_RE.fullmatch(key))
    is_zhipu_url = 'open.bigmodel.cn' in url
    if is_zhipu_key and not is_zhipu_url:
        return ('这把 Key 是智谱专有格式（id.secret），但 API 地址不是智谱'
                f'（当前：{url}）。钥匙和锁可能不是一家的，确定要这样保存吗？')
    if is_zhipu_url and not is_zhipu_key:
        return ('API 地址是智谱，但这把 Key 不像智谱发的（智谱是 id.secret 格式）。'
                '确定没拿错别家的 Key 吗？')
    return ''

@dataclass
class ChatSettings:
    enabled: bool=True; active_provider: str='openai-main'; default_system_prompt: str='你是一只可爱的桌面宠物，请用自然、友善的中文和用户交流。'; history_message_limit: int=40; history_char_limit: int=24000; providers: dict[str,ProviderConfig]=field(default_factory=dict); web_search: WebSearchSettings=field(default_factory=WebSearchSettings)
    def __post_init__(self): self.attach_runtime()
    def attach_runtime(self):
        """把全局联网设置挂到每个 provider 上，调用点拿 active_config 即可带上。"""
        for p in self.providers.values(): p.web_search=self.web_search
    @classmethod
    def defaults(cls):
        p=ProviderConfig('openai-main'); return cls(providers={p.provider_id:p})
    @classmethod
    def from_dict(cls,raw):
        raw=raw if isinstance(raw,dict) else {}; d=cls.defaults(); pr=raw.get('providers') if isinstance(raw.get('providers'),dict) else {}
        providers={str(k):ProviderConfig.from_dict(k,v) for k,v in pr.items() if isinstance(v,dict)} or d.providers
        active=str(raw.get('active_provider',next(iter(providers)))); active=active if active in providers else next(iter(providers))
        return cls(bool(raw.get('enabled',True)),active,str(raw.get('default_system_prompt',d.default_system_prompt)),_safe_int(raw.get('history_message_limit',40),40,lo=1),_safe_int(raw.get('history_char_limit',24000),24000,lo=100),providers,WebSearchSettings.from_dict(raw.get('web_search')))
    def to_dict(self,include_secrets=True):
        return {'enabled':self.enabled,'active_provider':self.active_provider,'default_system_prompt':self.default_system_prompt,'history_message_limit':self.history_message_limit,'history_char_limit':self.history_char_limit,'providers':{k:v.to_dict(include_secrets) for k,v in self.providers.items()},'web_search':self.web_search.to_dict(include_secrets)}
    @property
    def active_config(self):
        p=self.providers[self.active_provider]; p.web_search=self.web_search; return p

@dataclass
class ChatMessage:
    role: str; content: str; created_at: str=field(default_factory=utc_now); message_id: str=field(default_factory=lambda:uuid.uuid4().hex)
    # 仅供界面回显的思考过程 / 联网检索进度；不进模型上下文（PromptBuilder 只取 content）
    reasoning: str=''; activity: list[str]=field(default_factory=list)
    def to_dict(self):
        d=asdict(self)
        # 空值不落盘：旧会话文件格式不变，旧版本读到新文件也只会忽略这两个键
        if not d['reasoning']: d.pop('reasoning')
        if not d['activity']: d.pop('activity')
        return d
    @classmethod
    def from_dict(cls,raw):
        activity=raw.get('activity')
        activity=[str(x) for x in activity] if isinstance(activity,list) else []
        return cls(str(raw.get('role','user')),str(raw.get('content','')),str(raw.get('created_at',utc_now())),str(raw.get('message_id',uuid.uuid4().hex)),str(raw.get('reasoning') or ''),activity)

@dataclass
class ChatSession:
    session_id: str; character_id: str; provider_id: str; system_prompt: str; messages: list[ChatMessage]=field(default_factory=list); created_at: str=field(default_factory=utc_now); updated_at: str=field(default_factory=utc_now); custom_title: str=''; pinned: bool=False
    @classmethod
    def create(cls,character_id,provider_id,system_prompt): return cls(uuid.uuid4().hex,character_id,provider_id,system_prompt)
    def to_dict(self): return {'session_id':self.session_id,'character_id':self.character_id,'provider_id':self.provider_id,'system_prompt':self.system_prompt,'created_at':self.created_at,'updated_at':self.updated_at,'title':self.custom_title,'pinned':self.pinned,'messages':[m.to_dict() for m in self.messages]}
    @classmethod
    def from_dict(cls,raw): return cls(str(raw['session_id']),str(raw['character_id']),str(raw.get('provider_id','')),str(raw.get('system_prompt','')),[ChatMessage.from_dict(x) for x in raw.get('messages',[]) if isinstance(x,dict)],str(raw.get('created_at',utc_now())),str(raw.get('updated_at',utc_now())),str(raw.get('title',raw.get('custom_title',''))),bool(raw.get('pinned',False)))

    @property
    def title(self):
        """Upstream-compatible alias while modern UI keeps custom_title."""
        return self.custom_title

    @title.setter
    def title(self, value):
        self.custom_title = str(value or '')

# keyring 的"没有可用后端"占位实现：**全名精确匹配**，不扫名字子串。
# 扫子串（原来的 `"fail" not in low`）会误杀合法第三方后端——一个名为
# `company.failover.Keyring` 的可写后端会被判成不可用，等于把本来能存凭据的环境
# 判死（astra 第 13 轮）。这类判据只该认 keyring 自己的两个占位类。
_PLACEHOLDER_BACKENDS = frozenset({
    "keyring.backends.fail.Keyring",
    "keyring.backends.null.Keyring",
})


def _is_placeholder_backend(backend) -> bool:
    """这个后端只是"这台机器没有钥匙串"的占位实现（`fail` / `null`）吗？"""
    backend_type = type(backend)
    if f"{backend_type.__module__}.{backend_type.__name__}" in _PLACEHOLDER_BACKENDS:
        return True
    # 全名对不上时再看**类身份**：占位实现可能被继承/包装，或在别的模块路径下重导出。
    # 只比类、不猜名字，所以仍然不会误杀第三方后端。
    for module_name in ("keyring.backends.fail", "keyring.backends.null"):
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - 子系统不在就是"没有可比对的对象"
            continue
        placeholder = getattr(module, "Keyring", None)
        if isinstance(placeholder, type) and isinstance(backend, placeholder):
            return True
    return False


class SecretStore:
    def __init__(self,service_name='dsh-pet-standalone'):
        self.service_name=service_name
        try: import keyring
        except Exception: keyring=None
        self._keyring=keyring
        self._usable=None   # 惰性探测一次（后端在进程生命周期内不会换）

    def _backend_usable(self) -> bool:
        """**后端**真的能用吗（不只是 `import keyring` 成功）。

        模块在、后端不可用时写凭据会失败（`fail` 后端抛 ``NoKeyringError``，
        `null` 后端不抛但什么都不记）：界面说"已保存"、重启后主进程读到空串。
        **这是"读取为空"的成因，不是"服务端拒绝"的成因**——服务端回 401 并显示
        具体 key 尾号，只说明发出去的是非空凭据，具体为什么无效（key 失效 / 填错 /
        provider 不匹配 / 选错了旧的凭据条目）需要另查，别把两者混为一谈。
        """
        if self._keyring is None:
            return False
        try:
            backend = self._keyring.get_keyring()
        except Exception:
            return False
        return not _is_placeholder_backend(backend)

    @property
    def available(self):
        """可用 = 模块在 **且** 后端可用（两者缺一都是"存不了凭据"）。"""
        if self._usable is None:
            self._usable = self._backend_usable()
            if not self._usable:
                logging.getLogger("dsh-pet-standalone").warning(
                    "凭据存储不可用（系统钥匙串没有可用后端）：API Key 只能留在内存里，"
                    "重启后需要重新填写。打包版可能是 keyring 的 Windows 后端依赖"
                    "（pywin32-ctypes / win32ctypes）没随包进来，也可能只是这台机器的"
                    "系统钥匙串没启用/被策略禁用。")
        return self._usable

    def get(self,ref):
        if not self.available or not ref: return ''
        try: return str(self._keyring.get_password(self.service_name,ref) or '')
        except Exception as exc:
            logging.getLogger("dsh-pet-standalone").warning(
                "读取凭据失败（%s）：%s", ref, type(exc).__name__)
            return ''

    def set(self,ref,value):
        if not self.available or not ref: return False
        try: self._keyring.set_password(self.service_name,ref,value); return True
        except Exception as exc:
            # 失败不能静默：界面会显示"已保存"，用户下次启动就发现 Key 没了
            logging.getLogger("dsh-pet-standalone").warning(
                "保存凭据失败（%s）：%s", ref, type(exc).__name__)
            return False
