"""Trankit benchmark: state."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from . import worker_handle

workers: Dict[str, worker_handle.WorkerHandle] = {}


workers_started = False


workers_start_lock = threading.Lock()


cpu_opt_selection: Optional[Dict[str, Any]] = None


cpu_opt_start_lock = threading.Lock()
