"""Result persistence and evaluation around BAM's unchanged optimizer/simulator."""

import json
import runpy
from pathlib import Path

import numpy as np
import optuna
from bam.logs import Logs
from bam.simulate import Simulator

from motor_identification.devices.spec import MotorSpec


def evaluate(model, directory: Path, reset_period: float | None = None) -> float:
    """Use BAM rollouts and its per-log mean absolute position error."""
    scores = []
    for log in Logs(str(directory)).logs:
        positions, _, _ = Simulator(model).rollout_log(
            log, reset_period=reset_period, simulate_control=True
        )
        measured = np.array([entry["position"] for entry in log["entries"]])
        scores.append(float(np.mean(np.abs(np.asarray(positions) - measured))))
    if not scores:
        raise ValueError(f"No processed JSON logs under {directory}")
    return float(np.mean(scores))


def _save_best(study, namespace: dict, spec: MotorSpec) -> None:
    model = namespace["make_model"]()
    values = {key: parameter.value for key, parameter in model.get_parameters().items()}
    values.update(study.best_params)
    model.load_parameters_from_dict(values)
    metrics = {"training_mae_rad": float(study.best_value)}
    if namespace["args"].validation_kp > 0:
        metrics["validation_mae_rad"] = float(
            namespace["compute_score"](model, namespace["validation_batch"])
        )
    values.update(
        model=namespace["args"].model,
        actuator=spec.name,
        motor_spec=spec.to_dict(),
        identification=metrics,
    )
    Path(namespace["params_json_filename"]).write_text(json.dumps(values, indent=2) + "\n")
    print(f"Best training position MAE: {study.best_value:.8g} rad")
    if "validation_mae_rad" in metrics:
        print(f"Validation position MAE: {metrics['validation_mae_rad']:.8g} rad")


def fit(spec: MotorSpec) -> None:
    """Keep upstream optimization, adding snapshots to periodic and final outputs.

    BAM's pinned CLI has no library entry point. Its existing Study.optimize
    boundary supplies the module namespace; the temporary hook is always restored.
    Final persistence also runs on interruption after a completed trial, before
    upstream's final W&B upload on successful completion.
    """
    original = optuna.study.Study.optimize
    original_batch = Logs.make_batch

    def make_batch(logs):
        batch = original_batch(logs)
        steps = batch["dt"]
        if not np.all(steps == steps[0]):
            raise ValueError("BAM batch fitting requires logs resampled to the same dt")
        # The time grid is shared. A vector dt makes upstream's scalar
        # reset_period condition fail as soon as the batch contains two logs.
        batch["dt"] = float(steps[0])
        return batch

    def optimize(study, objective, *args, **kwargs):
        namespace = objective.__globals__
        callbacks = kwargs.get("callbacks", [])

        def with_snapshot(callback):
            def monitor(study, trial):
                last_write = namespace["last_log"]
                callback(study, trial)
                if namespace["last_log"] != last_write:
                    path = Path(namespace["params_json_filename"])
                    values = json.loads(path.read_text())
                    values["motor_spec"] = spec.to_dict()
                    path.write_text(json.dumps(values, indent=2) + "\n")

            return monitor

        kwargs["callbacks"] = [with_snapshot(callback) for callback in callbacks]
        try:
            return original(study, objective, *args, **kwargs)
        finally:
            # Only the upstream monitoring worker owns the output file.
            completed = study.get_trials(deepcopy=False, states=[optuna.trial.TrialState.COMPLETE])
            if callbacks and completed:
                _save_best(study, namespace, spec)

    try:
        optuna.study.Study.optimize = optimize
        Logs.make_batch = make_batch
        runpy.run_module("bam.fit", run_name="__main__")
    finally:
        optuna.study.Study.optimize = original
        Logs.make_batch = original_batch
