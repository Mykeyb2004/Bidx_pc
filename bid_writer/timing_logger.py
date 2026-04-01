"""
生成链路时序日志。

用于定位“正文已经显示完成，但生成弹窗迟迟不关闭”的具体卡点。
日志会追加写入仓库根目录下的 log/generation_timing.log。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()
_LOG_PATH = Path(__file__).resolve().parent.parent / "log" / "generation_timing.log"


def write_timing_log(event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "event": event,
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        **fields,
    }
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with _LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
