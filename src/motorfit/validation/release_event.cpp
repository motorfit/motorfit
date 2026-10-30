#include <mujoco/mujoco.h>
#include <algorithm>
#include <cmath>

// Frozen M1 PD/plant replay; only the torque-disable event changes.
// p = kp,kd,goal_speed,feedforward,torque_ratio,torque_min,torque_max.
// output columns: q,v,nominal_PD_torque,applied_torque,delayed_goal.
// diagnostics: gate_time,q_at_gate,v_at_gate,nominal_before_gate,
//              applied_before_gate,total_applied_impulse,split_count,
//              largest_post_gate_applied_torque.
extern "C" int rs05_release_event(mjModel* m, mjData* d, int n, int substeps,
    double release_time, const double* p, const double* targets,
    const double* enabled, double* output, double* diagnostics) {
  const double h = m->opt.timestep;
  const double epsilon = 1e-11;
  bool recorded_gate = false;
  double impulse = 0, max_post = 0;
  int split_count = 0;
  auto record_gate = [&](double t, double nominal) {
    diagnostics[0] = t;
    diagnostics[1] = d->qpos[0];
    diagnostics[2] = d->qvel[0];
    diagnostics[3] = nominal;
    diagnostics[4] = nominal*p[4];
    recorded_gate = true;
  };
  for (int k=0; k<n; ++k) {
    for (int j=0; j<substeps; ++j) {
      const int index = k*substeps+j;
      const double t = index*h;
      const double target = targets[index];
      const double nominal = std::clamp(p[0]*(target-d->qpos[0]) +
          p[1]*(p[2]-d->qvel[0]) + p[3], p[5], p[6]);
      const bool active = release_time < 0 ? enabled[k] != 0 : t < release_time-epsilon;
      const double applied = active ? nominal*p[4] : 0;
      if (release_time >= 0 && !active && !recorded_gate) record_gate(t, nominal);
      if (j==0) {
        double* o = output+5*k;
        o[0]=d->qpos[0]; o[1]=d->qvel[0]; o[2]=nominal;
        o[3]=applied; o[4]=target;
      }
      if (active && release_time >= 0 && release_time < t+h-epsilon) {
        // Preserve the pre-event PD sample. Only the actuator gate switches
        // inside this controller interval; the target/delay are not resampled.
        const double before = release_time-t, after = h-before;
        m->opt.timestep=before;
        d->ctrl[0]=applied;
        mj_step(m,d);
        impulse += applied*before;
        record_gate(release_time, nominal);
        m->opt.timestep=after;
        d->ctrl[0]=0;
        mj_step(m,d);
        m->opt.timestep=h;
        ++split_count;
      } else {
        d->ctrl[0]=applied;
        mj_step(m,d);
        impulse += applied*h;
        if (!active && release_time >= 0) max_post=std::max(max_post,std::abs(applied));
      }
      if (!std::isfinite(d->qpos[0]) || !std::isfinite(d->qvel[0])) return -1;
    }
  }
  diagnostics[5]=impulse;
  diagnostics[6]=split_count;
  diagnostics[7]=max_post;
  return 0;
}
