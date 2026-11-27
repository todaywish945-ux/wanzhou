# -*- coding: utf-8 -*-
"""联网检查、下载并启动 dsh-pet 更新安装包。

更新协议刻意保持为静态 JSON + 完整 Inno Setup 安装包：**仓库根目录的
update.json 是版本真源**（jsDelivr 多镜像），GitHub Releases API 只作兜底。
顺序不能反过来：本仓库的历史 Release 还留着上游 v4.4.x，API 优先会让
1.00 的用户天天收到假更新。安装包按 manifest 中的 URL 顺序回退，启动
安装器前校验 HTTPS、大小和 SHA-256，避免把网络错误当成可执行文件运行。

另有跨进程去重的「自动检查状态」读写（%APPDATA%/wanzhou-pet/updates/
auto-check.json）：三只桌宠是三个进程，状态文件保证一天只查一次、同一个
版本只提醒一次。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from . import __version__

APP_VERSION = __version__
# 自有发布仓库：GitHub Releases API 与三条 jsDelivr 镜像都由这一处拼出。
# 发布新版时在此仓库建 Release（或提交 update.json），改这一行即可整体切源。
REPO = 'todaywish945-ux/wanzhou'
RELEASE_API = f'https://api.github.com/repos/{REPO}/releases/latest'
REPO_URL = f'https://github.com/{REPO}'
QUARK_PAN_URL = 'https://pan.quark.cn/s/68fc681ae486'
_UPDATE_JSON_URLS = (
    f'https://cdn.jsdelivr.net/gh/{REPO}@main/update.json',
    f'https://fastly.jsdelivr.net/gh/{REPO}@main/update.json',
    f'https://gcore.jsdelivr.net/gh/{REPO}@main/update.json',
    # GitHub 官方直链：jsDelivr 各节点缓存刷新可能滞后几十分钟（实测发版
    # 5 分钟后三条镜像仍返回旧版），raw 是同一个文件的实时源，作为兜底。
    f'https://raw.githubusercontent.com/{REPO}/main/update.json',
)
_USER_AGENT = 'dsh-pet-standalone-updater'
_TRUSTED_ASSET_HOSTS = {
    'github.com',
    'raw.githubusercontent.com',
    'objects.githubusercontent.com',
    'github-releases.githubusercontent.com',
    'release-assets.githubusercontent.com',
    'cdn.jsdelivr.net',
    'fastly.jsdelivr.net',
    'gcore.jsdelivr.net',
    # GitHub 加速镜像（分件下载的回退线路；内容身份由 sha256 校验兜底，
    # 镜像本身不需要可信——投毒只会摘要不过、换下一条）
    'gh-proxy.com',
    'mirror.ghproxy.com',
}
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024

#: 自动检查节奏：启动后先查一次，运行中每 12 小时再查（长开不重启也能收到）。
#: 三进程共享状态文件，所以「一查」是全产品一次，不是每只宠一次。
AUTO_CHECK_INTERVAL_SECONDS = 12 * 60 * 60
#: 同一版本被打扰过一次后，隔 3 天才再提醒；版本变化立刻提醒。
AUTO_REMIND_INTERVAL_SECONDS = 3 * 24 * 60 * 60


class _TrustedRedirect(urllib.request.HTTPRedirectHandler):
    """逐跳校验重定向：初始 URL 过白名单不够——重定向目标也必须 https +
    白名单主机，不许被跳板带到别的源（素材镜像 host 进白名单后，这条
    就是防"镜像当跳板"的闸）。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _trusted_https_url(newurl):
            raise urllib.error.HTTPError(
                req.full_url, code, f"重定向目标不在可信白名单: {newurl}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def trusted_urlopen(req_or_url, *, timeout: float):
    """带**逐跳重定向校验**的 urlopen（更新器与素材包下载的统一出口）。"""
    return urllib.request.build_opener(_TrustedRedirect()).open(req_or_url, timeout=timeout)


def _fetch_json(url: str, timeout: float):
    """GET JSON；任何失败返回 None。"""
    try:
        req = urllib.request.Request(
            url,
            headers={'Accept': 'application/json', 'User-Agent': _USER_AGENT},
        )
        with trusted_urlopen(req, timeout=timeout) as resp:
            raw = resp.read(_MAX_MANIFEST_BYTES + 1)
            if len(raw) > _MAX_MANIFEST_BYTES:
                return None
            return json.loads(raw.decode('utf-8'))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _trusted_https_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(str(url))
    except ValueError:
        return False
    if parsed.scheme.lower() != 'https' or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip('.')
    if host in _TRUSTED_ASSET_HOSTS:
        if host.endswith('github.com') and host == 'github.com':
            return f'/{REPO}/' in parsed.path or parsed.path.startswith(f'/{REPO}/releases/')
        return True
    return False


def _asset_details(name: str, value) -> dict | None:
    """把旧版 name -> url 和新版结构化 asset 统一成内部结构。"""
    if isinstance(value, str):
        urls = [value]
        details = {}
    elif isinstance(value, dict):
        details = value
        urls = details.get('urls') or details.get('mirrors') or details.get('url')
        if isinstance(urls, str):
            urls = [urls]
        if not isinstance(urls, list):
            urls = []
    else:
        return None
    # 解析阶段保留旧版/测试/企业镜像地址；真正下载前再做 HTTPS +
    # trusted-origin 校验，这样检查更新仍能展示候选版本，同时不会执行不可信文件。
    urls = [str(url).strip() for url in urls if str(url).strip()]
    if not urls:
        return None
    result = {
        'name': str(details.get('fileName') or details.get('name') or name),
        'urls': urls,
        'url': urls[0],
        'size': int(details['size']) if str(details.get('size', '')).isdigit() else None,
        'sha256': str(details.get('sha256') or details.get('digest') or '').removeprefix('sha256:').strip().lower() or None,
        'platform': str(details.get('platform') or '').lower() or None,
        'kind': str(details.get('kind') or '').lower() or None,
        'variant': str(details.get('variant') or '').lower() or None,
    }
    return result


def _normalise_assets(raw_assets) -> tuple[dict[str, str], dict[str, dict]]:
    assets: dict[str, str] = {}
    details: dict[str, dict] = {}
    if not isinstance(raw_assets, dict):
        return assets, details
    for name, value in raw_assets.items():
        item = _asset_details(str(name), value)
        if item is None:
            continue
        key = str(name)
        assets[key] = item['url']
        details[key] = item
    return assets, details


def _release_from_payload(data: dict) -> dict | None:
    if not isinstance(data, dict) or not data.get('version'):
        return None
    assets, asset_details = _normalise_assets(data.get('assets') or {})
    return {
        'version': str(data['version']).lstrip('vV'),
        'html_url': str(data.get('html_url') or REPO_URL),
        # 开源版发布形态：Release 页 + 百度网盘直链（提取码单独带，别藏在 notes 里）。
        'download_url': str(data.get('download_url') or data.get('html_url') or REPO_URL),
        'download_code': str(data.get('download_code') or '').strip(),
        'notes': str(data.get('notes') or ''),
        'assets': assets,
        'asset_details': asset_details,
    }


def _plain_release_notes(markdown: str) -> str:
    """GitHub Release 正文是 Markdown，更新窗用的是 QLabel——原样塞进去会
    露出 `#` / `##` / 反引号和链接语法。这里只做展示用的无损降级：去掉标题
    符号与行内反引号，去掉列表前导符号，链接保留可读文字；不解释、不重写。
    """
    text = str(markdown or '')
    if not text:
        return ''
    lines = []
    for line in text.splitlines():
        value = line.strip()
        # Markdown 图片在纯文本里噪声最大，整行丢掉（Release 正文没有关键图）。
        if value.startswith('!['):
            continue
        value = re.sub(r'^#{1,6}\s*', '', value)          # # 标题
        value = re.sub(r'^[-*+]\s+', '· ', value)          # 无序列表
        value = re.sub(r'^\d+\.\s+', '', value)            # 有序列表
        value = value.replace('`', '')                     # 行内代码
        value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', value)  # 链接留文字
        value = re.sub(r'[*_]{1,2}([^*_]+)[*_]{1,2}', r'\1', value)  # 强调
        if value:
            lines.append(value)
    return '\n'.join(lines).strip()


def _release_from_github_payload(data: dict) -> dict | None:
    """把 GitHub Releases 的 JSON 折成与静态清单同构的结构。"""
    if not isinstance(data, dict) or not data.get('tag_name'):
        return None
    assets, asset_details = _normalise_assets({
        str(a['name']): {
            'url': str(a['browser_download_url']),
            'size': a.get('size'),
            'digest': a.get('digest'),
            'name': str(a['name']),
        }
        for a in data.get('assets', [])
        if a.get('name') and a.get('browser_download_url')
    })
    html_url = str(data.get('html_url') or REPO_URL)
    # 开源便携包没有 Inno Setup 安装包，兜底时把 zip 附件当下载入口，
    # 否则用户只拿到 tag 页还得自己找附件。
    portable_url = ''
    for name, url in assets.items():
        if name.lower().endswith('.zip'):
            portable_url = url
            break
    return {
        'version': str(data['tag_name']).lstrip('vV'),
        'html_url': html_url,
        'download_url': portable_url or html_url,
        'download_code': '',
        'notes': _plain_release_notes(data.get('body')),
        'assets': assets,
        'asset_details': asset_details,
    }


def latest_release(timeout: float = 5.0) -> dict | None:
    """多源查询最新版本信息（静态清单优先，GitHub API 兜底）。

    清单是发版时人工确认过的版本真源；GitHub 上遗留的 v4.4.x 是移植前
    上游的 Tag，不能被当成"新版本"推给 1.00 的用户。只有清单四条源
    （jsDelivr 三条 + GitHub raw）都取不到时，才退到 API 当作最后线索。
    """
    # 收集全部镜像的解析结果，取版本最高的。早期「第一条成功就返回」在
    # jsDelivr 节点缓存不同步时会读到旧版（实测三条镜像都停在 1.01、而
    # raw 直链已是 1.03），导致新版本推不出去。raw 兜底 + 取最高版本两者
    # 缺一不可：raw 实时但可能被墙，最高版本保证任何一条拿到新版都生效。
    #
    # 版本相同时还要挑「内容更新鲜」的那份：实测发版后 cdn/gcore 缓存的
    # update.json 版本号已是 1.03、但 download_url 还是旧的 GitHub 直链，
    # 而 raw 已是 gh-proxy 镜像。仅比版本会选中旧直链、用户下载撞墙。
    # 同版本时优先带镜像 download_url 的清单（它是作者后改的、更实时）。
    def _freshness(release: dict) -> tuple:
        version = version_parts(str(release.get("version", "")))
        download_url = str(release.get("download_url") or "")
        has_mirror = int("gh-proxy" in download_url or "ghproxy" in download_url)
        return (version, has_mirror)

    releases: list[dict] = []
    for url in _UPDATE_JSON_URLS:
        data = _fetch_json(url, timeout)
        result = _release_from_payload(data) if isinstance(data, dict) else None
        if result is not None:
            releases.append(result)
    if releases:
        return max(releases, key=_freshness)
    data = _fetch_json(RELEASE_API, timeout)
    return _release_from_github_payload(data) if isinstance(data, dict) else None


def version_parts(tag: str) -> list[int]:
    out: list[int] = []
    for seg in str(tag).lstrip('vV').split('.'):
        digits = ''
        for ch in seg:
            if ch.isdigit():
                digits += ch
            else:
                break
        out.append(int(digits) if digits else 0)
    return out


def is_newer(latest_tag: str, current: str | None = None) -> bool:
    # 默认参数不能在定义时绑定 APP_VERSION：那样模块加载后改版本（测试注入、
    # 运行期热替换）会读到旧值，版本判断永远用启动那一刻的版本。
    if current is None:
        current = APP_VERSION
    return version_parts(latest_tag) > version_parts(current)


def select_windows_installer(release: dict, *, include_chat: bool = True) -> dict | None:
    """按当前 Windows 构建变体选择 Inno Setup 安装包。"""
    if os.name != 'nt' or not isinstance(release, dict):
        return None
    wanted = 'dsh-pet-standalone-webm-chat-setup.exe' if include_chat else 'dsh-pet-standalone-webm-setup.exe'
    details = (release.get('asset_details') or {}).get(wanted)
    if details is not None:
        return details
    url = (release.get('assets') or {}).get(wanted)
    if url:
        return _asset_details(wanted, url)
    return None


def _safe_filename(name: str) -> str:
    value = Path(str(name)).name
    value = re.sub(r'[^A-Za-z0-9._() -]+', '_', value).strip(' .')
    return value or 'dsh-pet-update.exe'


def download_asset(
    asset: dict,
    target_dir: str | os.PathLike,
    *,
    timeout: float = 30.0,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    """下载并验证安装包；某个镜像失败会尝试下一个镜像。"""
    urls = list(asset.get('urls') or ([asset.get('url')] if asset.get('url') else []))
    expected_size = asset.get('size')
    expected_hash = str(asset.get('sha256') or '').lower() or None
    if not any(_trusted_https_url(url) for url in urls):
        raise RuntimeError('untrusted URL: ' + (urls[0] if urls else ''))
    if expected_size is None or expected_hash is None:
        raise ValueError('更新资产缺少 size 或 SHA-256，已停止自动安装')
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / _safe_filename(asset.get('name') or 'dsh-pet-update.exe')
    errors = []
    for url in urls:
        if not _trusted_https_url(url):
            errors.append(f'untrusted URL: {url}')
            continue
        partial = final_path.with_suffix(final_path.suffix + '.part')
        digest = hashlib.sha256()
        total = int(expected_size) if expected_size is not None else None
        received = 0
        try:
            req = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
            with trusted_urlopen(req, timeout=timeout) as response, partial.open('wb') as output:
                header_total = response.headers.get('Content-Length')
                if total is None and header_total and header_total.isdigit():
                    total = int(header_total)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > _MAX_DOWNLOAD_BYTES or (total is not None and received > total):
                        raise ValueError('download exceeds declared size')
                    digest.update(chunk)
                    output.write(chunk)
                    if progress:
                        progress(received, total)
            if total is not None and received != total:
                raise ValueError(f'size mismatch: expected {total}, got {received}')
            actual_hash = digest.hexdigest()
            if expected_hash and actual_hash != expected_hash:
                raise ValueError(f'SHA-256 mismatch: expected {expected_hash}, got {actual_hash}')
            partial.replace(final_path)
            return final_path
        except (urllib.error.URLError, OSError, ValueError) as exc:
            errors.append(f'{url}: {exc}')
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
    raise RuntimeError('；'.join(errors) or '没有可用的下载地址')


def select_portable_archive(release: dict) -> dict | None:
    """选便携 zip 资产（带 size + sha256 才可用）。

    便携版没有 Inno Setup 安装包，一键更新走「下载 zip → 校验 → 解压到暂存
    → 独立脚本替换程序目录」。资产名以 ``-portable.zip`` 结尾，摘要可由
    manifest 的 sha256 或 GitHub 的 digest 提供。
    """
    if not isinstance(release, dict):
        return None
    details = release.get('asset_details') or {}
    for name, item in details.items():
        if str(name).lower().endswith('.zip') and item.get('size') is not None and item.get('sha256'):
            return item
    return None


def stage_portable_update(asset: dict, config_dir: str | os.PathLike, *,
                          timeout: float = 60.0,
                          progress: Callable[[int, int | None], None] | None = None) -> Path:
    """下载并解压便携包到暂存目录，返回解压后的程序根目录（含 exe）。

    只写 ``%APPDATA%/wanzhou-pet/updates/staging``，绝不碰正在运行的程序目录。
    真正的目录替换由独立脚本在桌宠全部退出后完成。
    """
    import zipfile

    cache = update_cache_dir(config_dir)
    staging = cache / 'staging'
    staging.mkdir(parents=True, exist_ok=True)
    archive = download_asset(asset, cache, timeout=timeout, progress=progress)
    # 每次更新前清空 staging，避免旧版本残留混进新目录。
    for child in staging.iterdir():
        if child.is_dir():
            import shutil
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        # 防 zip-slip：只接受解压后仍在 staging 内的条目。
        for member in bundle.namelist():
            target = (staging / member).resolve()
            if not str(target).startswith(str(staging.resolve()) + os.sep) and target != staging.resolve():
                raise RuntimeError(f'更新包包含越界路径：{member}')
        bundle.extractall(staging)
    root = staging / 'wanzhou-pet'
    if not (root / 'wanzhou-pet.exe').is_file():
        raise RuntimeError('更新包缺少 wanzhou-pet.exe，已停止')
    return root


def _ps_quote(value: object) -> str:
    """PowerShell 单引号字符串转义（路径里的单引号 doubled）。"""
    return "'" + str(value).replace("'", "''") + "'"


def write_portable_update_script(staged_root: str | os.PathLike,
                                 app_dir: str | os.PathLike, *,
                                 config_dir: str | os.PathLike) -> Path:
    """生成独立 PowerShell 脚本：等桌宠退出 → 备份旧目录 → 就位新版 → 重启。

    脚本放在系统临时目录，**不在被替换的程序目录里**，否则替换时会把脚本自己
    删掉。备份目录保留到新版本启动成功后才清理，失败则回滚。
    """
    staged = Path(staged_root).resolve()
    target = Path(app_dir).resolve()
    log = update_cache_dir(config_dir) / 'portable-update.log'
    backup = target.with_name(f'{target.name}.bak-{int(time.time())}')
    script = Path(tempfile.gettempdir()) / f'wanzhou-update-{os.getpid()}.ps1'
    ps = f"""$ErrorActionPreference = 'Stop'
$target = {_ps_quote(str(target))}
$staged = {_ps_quote(str(staged))}
$backup = {_ps_quote(str(backup))}
$log = {_ps_quote(str(log))}
# 日志目录可能还不存在（首次更新 / 状态文件被清理过），先建再写。
$logDir = Split-Path -Parent $log
if (-not (Test-Path $logDir)) {{ New-Item -ItemType Directory -Path $logDir -Force | Out-Null }}
function W($m) {{ Add-Content -Path $log -Value ((Get-Date).ToString('o') + ' ' + $m) -Encoding utf8 }}
try {{
  W 'update script started'
  # 等旧进程自己收尾 3 秒，再强制结束残留；只认本产品进程名。
  Start-Sleep -Seconds 3
  Get-Process -Name 'wanzhou-pet' -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 1
  if (Test-Path $backup) {{ Remove-Item -LiteralPath $backup -Recurse -Force }}
  Move-Item -LiteralPath $target -Destination $backup
  try {{
    Move-Item -LiteralPath $staged -Destination $target
    Start-Process -FilePath (Join-Path $target 'wanzhou-pet.exe') -WorkingDirectory $target
    Start-Sleep -Seconds 3
    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    W 'update OK'
  }} catch {{
    if ((Test-Path $backup) -and -not (Test-Path $target)) {{
      Move-Item -LiteralPath $backup -Destination $target
      W 'rolled back'
    }}
    throw
  }}
}} catch {{
  W ('FAILED: ' + $_.Exception.Message)
  exit 1
}}
"""
    script.write_text(ps, encoding='utf-8-sig')  # BOM：让 Windows PowerShell 正确读中文路径
    return script


def start_portable_update(script: str | os.PathLike) -> None:
    """以脱离父进程的方式启动更新脚本；父进程随后即可退出。"""
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
        cwd=str(Path(script).parent), close_fds=True, creationflags=flags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def can_auto_install() -> bool:
    """仅冻结的 Windows 安装版允许自动拉起安装器。"""
    return os.name == 'nt' and bool(getattr(__import__('sys'), 'frozen', False))


def start_installer(installer_path: str | os.PathLike) -> None:
    """启动 Inno Setup 安装器；调用方随后退出当前应用。"""
    path = str(Path(installer_path).resolve())
    if os.name != 'nt':
        raise RuntimeError('当前平台不支持自动安装，请打开下载页手动更新。')
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(
        [path, '/SILENT', '/CLOSEAPPLICATIONS', '/NORESTART'],
        close_fds=True,
        creationflags=flags,
        cwd=str(Path(path).parent),
    )


def update_cache_dir(config_dir: str | os.PathLike | None = None) -> Path:
    if config_dir:
        return Path(config_dir) / 'updates'
    return Path(tempfile.gettempdir()) / 'dsh-pet-updates'


def auto_check_state_path(config_dir: str | os.PathLike) -> Path:
    """跨进程共享的自动检查状态文件（三只桌宠同目录，抢同一份）。"""
    return Path(config_dir) / 'updates' / 'auto-check.json'


def _auto_check_state(config_dir: str | os.PathLike) -> dict:
    from .config_write_lock import read_json_dict

    data, status = read_json_dict(auto_check_state_path(config_dir))
    return data if status == 'ok' and isinstance(data, dict) else {}


def _modify_auto_check_state(config_dir: str | os.PathLike, **fields) -> None:
    """目录锁内重读→改→原子写；状态文件损坏时按空表重建（它只是缓存）。"""
    from .config_write_lock import locked_update_json

    def mutate(current: dict) -> dict:
        current.update(fields)
        return current

    try:
        locked_update_json(
            auto_check_state_path(config_dir), mutate, on_broken='replace')
    except Exception:  # noqa: BLE001 - ConfigWriteError 等非标准异常也要收口
        # 状态写不进去不该拖垮启动：最坏是多查一次网，不影响正确性。
        logging.getLogger(__name__).debug('更新检查状态写入失败', exc_info=True)


def auto_check_enabled(config_dir: str | os.PathLike) -> bool:
    """自动检查开关：真源是主配置 config.json（设置页写那里），缺省开。"""
    from .config_write_lock import read_json_dict

    data, status = read_json_dict(Path(config_dir) / 'config.json')
    if status != 'ok' or not isinstance(data, dict) or 'auto_check_update' not in data:
        return True
    return data['auto_check_update'] is not False


def auto_check_due(config_dir: str | os.PathLike, *, now: float | None = None,
                   interval: float = AUTO_CHECK_INTERVAL_SECONDS) -> bool:
    """距离上一次检查是否够间隔（首次/状态损坏都按「该查了」处理）。"""
    now = time.time() if now is None else now
    try:
        last = float(_auto_check_state(config_dir).get('last_check', 0) or 0)
    except (TypeError, ValueError, OverflowError):
        return True
    return (now - last) >= interval


def mark_auto_check(config_dir: str | os.PathLike, *, now: float | None = None) -> None:
    """先把检查时间占住，再发网络请求——三进程并发启动时只有一只会查。"""
    _modify_auto_check_state(config_dir, last_check=time.time() if now is None else now)


def should_notify_update(config_dir: str | os.PathLike, version: str, *,
                         now: float | None = None,
                         interval: float = AUTO_REMIND_INTERVAL_SECONDS) -> bool:
    """同一版本提醒过就静默到下次提醒窗口；新版本立即提醒。"""
    now = time.time() if now is None else now
    state = _auto_check_state(config_dir)
    if str(state.get('notified_version', '')).lstrip('vV') != str(version).lstrip('vV'):
        return True
    try:
        notified_at = float(state.get('notified_at', 0) or 0)
    except (TypeError, ValueError, OverflowError):
        return True
    return (now - notified_at) >= interval


def mark_update_notified(config_dir: str | os.PathLike, version: str, *,
                         now: float | None = None) -> None:
    _modify_auto_check_state(
        config_dir,
        notified_version=str(version).lstrip('vV'),
        notified_at=time.time() if now is None else now,
    )
