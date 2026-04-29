import gc
import time


class PerformanceTracker:
    """Measures per-frame timing and memory allocation for on-device profiling.

    Call ``start_frame`` at the beginning of each frame, bracket update and
    render work with ``start_update_time``/``add_update_time`` and
    ``start_render_time``/``add_render_time``, then call ``complete_frame`` at
    the end. Aggregated stats are printed at ``log_interval`` second intervals.
    """

    def __init__(self, log_interval: float = 5.0):
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
        self._memory_before = 0
        self._update_started_at = 0.0
        self._render_started_at = 0.0

    def start_frame(self) -> None:
        self._memory_before = gc.mem_alloc()

    def start_update_time(self) -> None:
        self._update_started_at = time.monotonic()

    def add_update_time(self) -> None:
        self.update_time_total += time.monotonic() - self._update_started_at

    def start_render_time(self) -> None:
        self._render_started_at = time.monotonic()

    def add_render_time(self) -> None:
        self.render_time_total += time.monotonic() - self._render_started_at

    def complete_frame(self, current_time: float) -> None:
        """Record memory allocation for this frame and print stats
        if the log interval has elapsed."""
        memory_after = gc.mem_alloc()
        available_memory = gc.mem_free()

        memory_delta = memory_after - self._memory_before
        self.memory_delta_total += memory_delta
        if memory_delta > 0:
            self.memory_allocated_total += memory_delta
        if memory_delta > self.memory_delta_peak:
            self.memory_delta_peak = memory_delta
        self.last_memory_delta = memory_delta

        self.frame_count += 1
        if current_time > self.next_log_time:
            fps = self.frame_count / (current_time - self.start_time)
            update_avg = self.update_time_total / self.frame_count
            render_avg = self.render_time_total / self.frame_count
            mem_delta_avg = self.memory_delta_total / self.frame_count
            mem_alloc_avg = self.memory_allocated_total / self.frame_count
            print(
                f"__FPS: {fps:.2f}, "
                f"Update Time: {update_avg:.4f}s, "
                f"Render Time: {render_avg:.4f}s, "
                f"Mem Delta Avg: {mem_delta_avg:.2f}B, "
                f"Mem Alloc Avg: {mem_alloc_avg:.2f}B, "
                f"Mem Delta Last: {self.last_memory_delta}B, "
                f"Mem Delta Peak: {self.memory_delta_peak}B, "
                f"Mem Used: {memory_after}B, "
                f"Mem Free: {available_memory}B"
            )
            self.next_log_time = current_time + self.log_interval
