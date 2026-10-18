import { assess } from './policy.uc';

// One owner. Events cannot accelerate or postpone the board's UVLO timer.
export function create_guard(profile, runtime) {
    const state = { active: false, count: 0 };
    let scheduled = false, shutting_down = false;
    function evaluate(tick) {
        if (tick) scheduled = false;
        if (shutting_down) return;
        const result = assess(runtime.read(), profile, state, tick);
        if (result.reason) {
            shutting_down = true;
            runtime.cancel();
            runtime.poweroff(result.reason);
        }
        else if (result.next != null) {
            if (!scheduled) {
                scheduled = true;
                runtime.schedule(result.next);
            }
        }
        else if (scheduled) {
            runtime.cancel();
            scheduled = false;
        }
    }
    return { event: () => evaluate(false), tick: () => evaluate(true) };
};
