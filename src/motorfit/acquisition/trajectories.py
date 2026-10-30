"""The soccer-bam sweep and thin wrappers around BAM's built-in trajectories."""

from math import sin

from bam.trajectory import trajectories

NAMES = (*trajectories, "soccer_sweep")


class Trajectory:
    def __init__(self, recording: dict):
        self.name = recording.get("trajectory", "sin_time_square")
        self.builtin = trajectories.get(self.name)
        if self.builtin is None and self.name != "soccer_sweep":
            raise ValueError(f"Unknown trajectory: {self.name}")
        native_duration = 30.0 if self.name == "soccer_sweep" else self.builtin.duration
        self.duration = float(recording.get("duration_s", native_duration))
        self.amplitude = float(recording.get("amplitude", 1.0))
        self.sweep_k = float(recording.get("sweep_k", 0.1))
        self.metadata = {
            "name": self.name,
            "duration_s": self.duration,
            "amplitude_scale": self.amplitude,
        }
        if self.name == "soccer_sweep":
            self.metadata.update(formula="amplitude * sin(sweep_k * t**2)", sweep_k=self.sweep_k)
        else:
            self.metadata.update(
                source=f"bam.trajectory.{type(self.builtin).__name__}",
                native_duration_s=self.builtin.duration,
                time_scale=self.builtin.duration / self.duration,
            )

    def __call__(self, t: float) -> tuple[float, bool]:
        if self.name == "soccer_sweep":
            return self.amplitude * sin(self.sweep_k * t * t), True
        angle, enabled = self.builtin(t * self.builtin.duration / self.duration)
        return self.amplitude * float(angle), bool(enabled)
