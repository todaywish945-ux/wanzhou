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
)
_USER_AGENT = 'dsh-pet-standalone-updater'
_TRUSTED_ASSET_HOSTS = {
    'github.com',
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
    return {
        'version': str(data['tag_name']).lstrip('vV'),
        'html_url': html_url,
        'download_url': html_url,
        'download_code': '',
        'notes': str(data.get('body') or ''),
        'assets': assets,
        'asset_details': asset_details,
    }


def latest_release(timeout: float = 5.0) -> dict | None:
    """多源查询最新版本信息（静态清单优先，GitHub API 兜底）。

    清单是发版时人工确认过的版本真源；GitHub 上遗留的 v4.4.x 是移植前
    上游的 Tag，不能被当成"新版本"推给 1.00 的用户。只有清单三条镜像
    都取不到时，才退到 API 并把它当作最后线索。
    """
    for url in _UPDATE_JSON_URLS:
        data = _fetch_json(url, timeout)
        result = _release_from_payload(data) if isinstance(data, dict) else None
        if result is not None:
            return result
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


def is_newer(latest_tag: str, current: str = APP_VERSION) -> bool:
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
