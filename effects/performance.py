import gc
import time


class PerformanceTracker:
    """Measures per-frame timing and memory allocation for on-device profiling.

    Call ``start_frame`` at the beginning of each frame, bracket update and
    render work with ``start_update_time``/``add_update_time`` and
    ``start_render_time``/``add_render_time``, then call ``complete_frame`` at
    the end. Aggregated stats are printed at ``log_interval`` second intervals.
    """

    def __init__(self, log_interval: float = 5.0) -> None:
        now = time.monotonic()
        self.log_interval = log_interval
        self.frame_count = 0
        self.start_time = now
        self.next_log_time = now
        self.update_time_total = 0.0
        self.render_time_total = 0.0
        self.memory_delta_total = 0
        self.memory_allocated_total = 0
        self.memory_delta_peak = 0
        self.last_memory_delta = 0
        self.frame_time_peak = 0.0
        self.last_frame_end = now
        self.last_mem_used = 0
        self.last_mem_free = 0
        self._memory_before = 0
        self._update_started_at = 0.0
        self._render_started_at = 0.0
        self._frame_started_at = 0.0

    def start_frame(self) -> None:
        """Record the heap allocation baseline and start time for this frame."""
        self._memory_before = gc.mem_alloc()
        self._frame_started_at = time.monotonic()

    def start_update_time(self) -> None:
        """Record the start of the update phase."""
        self._update_started_at = time.monotonic()

    def add_update_time(self) -> None:
        """Accumulate elapsed time since the last ``start_update_time`` call."""
        self.update_time_total += time.monotonic() - self._update_started_at

    def start_render_time(self) -> None:
        """Record the start of the render phase."""
        self._render_started_at = time.monotonic()

    def add_render_time(self) -> None:
        """Accumulate elapsed time since the last ``start_render_time`` call."""
        self.render_time_total += time.monotonic() - self._render_started_at

    def complete_frame(self) -> bool:
        """Close the current frame and report whether a log interval elapsed.

        Returns:
            ``True`` if this frame crossed the ``log_interval`` boundary -- the
            caller should emit its stats line via
            :func:`~hardware.shared.profiler_report.print_stats_line`;
            ``False`` otherwise.
        """
        now = time.monotonic()
        memory_after = gc.mem_alloc()
        available_memory = gc.mem_free()

        memory_delta = memory_after - self._memory_before
        self.memory_delta_total += memory_delta
        if memory_delta > 0:
            self.memory_allocated_total += memory_delta
        if memory_delta > self.memory_delta_peak:
            self.memory_delta_peak = memory_delta
        self.last_memory_delta = memory_delta
        self.last_mem_used = memory_after
        self.last_mem_free = available_memory

        frame_time = now - self._frame_started_at
        if frame_time > self.frame_time_peak:
            self.frame_time_peak = frame_time

        self.frame_count += 1
        self.last_frame_end = now

        if now > self.next_log_time:
            self.next_log_time = now + self.log_interval
            return True
        return False
