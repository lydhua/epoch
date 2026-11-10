# Research note: mastery, timing, and maintenance

Reviewed 2026-11-05. This is a targeted literature review, not a systematic review.
The user's old spreadsheet criterion was at least three **total attempts** plus
an independent solve. That convenience rule is not an Epoch requirement.

## Findings and applicability

### 1. Successful retrieval and spacing matter more than a raw attempt counter

Work on successive relearning supports practicing retrieval again across spaced
sessions, rather than equating exposure with durable learning [1]. A failure with
feedback may contribute to learning, but three exposures do not establish three
successful retrievals. Evidence from associative/factual tasks does not establish
a universal number of repetitions for programming.

**Implication:** distinguish exposure count, independent successes, assistance,
and the delays across which success has been demonstrated. Do not discard failure
events, and do not treat repeating a just-read solution as strong retention evidence.

### 2. There is relevant programming evidence, with important limits

YeckehZaare and Resnick (2025) compared incentives for practicing on more days
with incentives for answering more questions. In their introductory programming
within-course experiment, the analyzed sample was 143 students; mean final exam
scores were 85.3% versus 81.7%, and mean practice days 38.5 versus 17.3 [2]. Both
groups used the same adaptive practice tool. Thus this is evidence for the
spacing incentive, not proof of a new adaptive algorithm's superiority.

The tool included multiple-choice and short active-code questions; median answer
times were 19 and 50 seconds respectively. A second instructor-randomized
experiment measured practice behavior, not comparable exam outcomes. The study
does not validate repeating 30-minute LeetCode problems or an interview-readiness
threshold, and the within-course analysis excluded some randomized students.

**Implication:** favor distributed practice and measure actual practice days.
Do not promise interview gains from short-question programming studies.

### 3. Time is useful evidence, not a substitute for correctness

Mettler et al. (2020) tested adaptive spacing incorporating response time and
accuracy, including objective mastery/dropout criteria [3]. In their second
experiment, adaptive and random schedules had the same mastery/dropout criteria;
adaptive scheduling produced greater learning efficiency. The tasks were map
identification, not programming. Their speed thresholds cannot transfer directly
to complex problem solving, and efficiency is distinct from raw retention.

**Implication:** keep two visible dimensions: independent solving and time to
solve. Slow success remains success. A fast copied solution is not independent
success. Compare time within a user and comparable activities, and allow personal
goals. Missing timing is unknown, not zero. An abandoned timed attempt is not a
successful solve with a short duration; future time-to-success modeling should
account for incomplete/censored observations.

### 4. Self-assessment should supplement observed performance

Karpicke, Butler, and Roediger (2009) surveyed 177 students about study strategies
and discussed illusions of competence and underuse of retrieval practice [4].
This supports caution about relying solely on perceived familiarity; it does not
quantify the predictive value of Epoch's proposed confidence ratings.

**Implication:** ask for outcome first, then optional confidence or perceived
effort. Keep "review sooner" and "snooze" as explicit user preferences. Never
silently relabel a failed attempt as successful because confidence is high.

### 5. The retention horizon matters

Cepeda et al. (2008) studied fact retention with over 1,350 participants, review
gaps up to roughly 3.5 months, and final tests up to a year later [5]. Optimal
spacing depended on the later test delay; wider spacing was not always better.

**Implication:** long-term maintenance and preparation for an interview next week
are different goals. Record optional target dates and a realistic time budget.
Do not infer a universally optimal retention target or interval from this study.

### 6. Learned scheduling is established prior art

Anki's official documentation says FSRS learns parameters from review history,
supports desired retention, and keeps graduated cards in review [6]. It also
states that recorded answer time does not influence scheduling. Settles and
Meeder's trainable half-life regression is another established learned-memory
approach in language learning [7]. These sources establish relevant prior art,
not their superiority for programming.

**Implication:** benchmark against meaningful alternatives. Start with a shared
forgetting-curve baseline and evaluate an FSRS comparator once an explicit,
documented mapping of coding outcomes to its ratings exists. Do not present
"uses ML" or a neural network as evidence of novelty or better scheduling.

## Recommended pilot policy

The [baseline prototype](../practice-v1.md) now implements a configurable version
of the learning/consolidation/maintenance workflow below. It is a product heuristic,
not validation of these thresholds or of real-world learning gains. Learned
scheduling and prospective comparisons remain future work.

1. **Learning:** no independent success demonstrated yet.
2. **Consolidating:** an independent solve has occurred, but evidence of delayed
   retention is limited. Repetitions immediately after solution study do not by
   themselves justify long intervals.
3. **Maintenance:** independent success demonstrated again after a meaningful
   delay. Keep a finite next review and bring it forward after a lapse. A pilot
   could require two independent successes on separate days, but the count and
   delay are product heuristics to tune, not research-proven LeetCode thresholds.
4. **Timing goal:** show separately whether an independent solve met the user's
   time goal. Initially do not demote every slow success to failure. Later predict
   independent success and timely independent success as separate targets if data
   supports it.
5. **User agency:** permit earlier review, snoozing, and explicit archiving. Medium
   and hard items remain in maintenance; do not assume difficulty alone identifies
   how quickly a particular user forgets.
6. **Model integration:** eventually select intervals from calibrated predicted
   success at candidate delays, with evidence guards and a transparent cold-start
   fallback. Avoid showing confident personalized estimates before validation.

Repeated success on one familiar item is not proof of transferable skill.
Future evaluation should include unseen related problems, alongside retention
of previously studied ones. No source reviewed establishes the ideal LeetCode
mastery threshold, default solve-time limit, or universal maintenance interval.

## Validation plan

Compare the spreadsheet rule, a transparent spaced-success heuristic, and learned
predictions on held-out chronological attempts. Measure calibration, independent
success, timely independent success, and review minutes, stratified by difficulty
and history length. Distinguish missing timing and self-reported outcomes.
Offline prediction scores do not establish a causal scheduling benefit: that
requires prospective evaluation, preferably an opt-in randomized comparison.
Evaluate transfer separately using unseen related problems. Synthetic experiments
remain pipeline/assumption checks, not evidence of real interview gains.

## Sources

1. Rawson & Dunlosky (2011), *Optimizing schedules of retrieval practice for durable
   and efficient learning: How much is enough?*
   https://pubmed.ncbi.nlm.nih.gov/21707204/
   Abstract-level evidence only in this review; full text was not accessible.
2. YeckehZaare & Resnick (2025), *Counting days is a spacing incentive that unlocks
   the potential of low GPA students.* Full text:
   https://pmc.ncbi.nlm.nih.gov/articles/PMC12141441/
3. Mettler et al. (2020), *Comparing Adaptive and Random Spacing Schedules during
   Learning to Mastery Criteria.* Full text:
   https://pmc.ncbi.nlm.nih.gov/articles/PMC8324179/
4. Karpicke, Butler, & Roediger (2009), *Metacognitive strategies in student
   learning: Do students practise retrieval when they study on their own?*
   University-hosted abstract:
   https://profiles.wustl.edu/en/publications/metacognitive-strategies-in-student-learning-do-students-practise/
5. Cepeda et al. (2008), *Spacing effects in learning: A temporal ridgeline of
   optimal retention.* Author-hosted abstract:
   https://www.yorku.ca/ncepeda/publications/CVRWP2008.html
6. Anki Manual, *Deck Options*, FSRS, Timers, and Maximum Interval sections:
   https://docs.ankiweb.net/deck-options.html
7. Settles & Meeder (2016), *A Trainable Spaced Repetition Model for Language
   Learning.* Bibliographic/approach reference; not evaluated here in full:
   https://aclanthology.org/P16-1174/
