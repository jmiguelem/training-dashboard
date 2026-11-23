"""General endurance-training principles given to the coach.

Written in our own words from public coaching sources, not copied. Edit freely: this text is sent to the
coach as background. The athlete's own data, profile and safety always override it.
"""

KNOWLEDGE_VERSION = 2

BASE_KNOWLEDGE = """\
General endurance-training principles. Use them as a template, then adapt to the athlete's data and goal. If the \
athlete's data, profile or safety disagrees with anything here, the athlete wins.

Periodization (Joe Friel, The Triathlete's Training Bible): Base, then Build, then Peak, then Race. Base builds general aerobic \
fitness and technique. Build adds race-specific and higher-intensity work. Peak sharpens. Load rises for 2 to 3 weeks then drops \
for a recovery week (3:1 for older or slower-recovering athletes, 4:1 otherwise). His plans assume a completed base and abilities \
like swimming about an hour, riding about 3 hours and running about 2 hours in single sessions.

Intensity balance: about 80 percent of training time at low intensity and about 20 percent moderate to hard (Matt Fitzgerald and \
David Warden, 80/20 Triathlon; supported by Stephen Seiler's research on how elite endurance athletes train, where evidence from \
controlled trials is still limited). The common mistake is the moderate-intensity rut: too many sessions that are too hard to \
recover from and too easy to improve. Make easy days truly easy.

Aerobic base by heart rate (Phil Maffetone, used by Mark Allen): keep base work at or below roughly 180 minus age bpm, minus about \
5 for people returning from a break or training inconsistently. It is a conservative cap, not a precise zone. Re-test periodically \
at a fixed easy heart rate and watch pace improve. Prefer the athlete's own zones from the profile when both exist.

Strength alongside endurance (coaching and research summaries): 2 to 3 sessions a week in base, 1 to 2 in build, 1 maintenance \
session in the race-specific phase. About 2 sessions a week for 8 to 12 weeks is enough to help endurance. Avoid heavy lifting on \
the same day as hard intervals and keep heavy leg work away from the day before a key run or ride. When an athlete lifts more than \
this, treat the extra sessions as load: shorten them or lower leg volume as run and bike volume rises.

Applying it:
- Work out the phase from weeks to race and the athlete's CURRENT capacity (recent weeks), not their best ever. Rebuild gradually \
from what they have done lately.
- Suggested phase by weeks to race: more than 16 base, 8 to 16 build, 3 to 8 peak and race-specific, 1 to 2 taper, 0 race week. \
If the athlete is behind where this implies, say so and plan the next step, not a leap.
- Keep any week-to-week rise in total training time near 10 percent, and add a recovery week after 3 rising weeks.
- Keep every sport the athlete trains in the plan over a multi-week view. If a sport was left out this week, it should return soon, in a short easy \
session, so the skill and feel are not lost.
"""

# Added on top of BASE_KNOWLEDGE for a given goal type.
TRIATHLON_KNOWLEDGE = """\
Typical structure of beginner 70.3 plans (common to published 12 to 25 week plans from TrainingPeaks coaches, \
Tri247, Marathon Handbook and others):
- 2 to 3 sessions per sport per week for swim, bike and run, plus 1 strength session. The bike carries the most hours.
- One longer session per sport each week, usually on the weekend, with easier sessions in between.
- Plans start gently (run/walk intervals for new runners) and mostly stay easy (zone 2), layering in tempo or \
interval work later.
- Longest sessions peak about 2 to 3 weeks before the race: roughly a 16-20 km run, an 80-100 km easy ride and a swim of \
about 2 km. Do not repeat the peak distance on race day's eve.
- Brick sessions (bike then run) start in the build phase, lengthen over time, and a race-simulation brick or two appears \
mid-to-late plan.
- Recovery weeks come every 3rd or 4th week with clearly less volume. Taper over the last 1 to 3 weeks: less volume, a \
little intensity kept.
- Time and entry level: first-timer plans run 14 to 25 weeks and assume the athlete can already run/walk, swim continuously \
and ride for an hour or more. If the time to the race is short for the athlete's current base, say so plainly and prioritise \
the weakest sport; do not compress progress to fit.
"""

EXTRA_BY_GOAL = {"triathlon": TRIATHLON_KNOWLEDGE}


def knowledge_for(goal_type: str) -> str:
    return BASE_KNOWLEDGE + EXTRA_BY_GOAL.get(goal_type, "")
