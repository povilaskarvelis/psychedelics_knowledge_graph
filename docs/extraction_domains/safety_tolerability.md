Focus on safety and tolerability evidence: adverse events, tolerability,
toxicity, discontinuation, abuse liability, contraindications, physiological
safety, serious adverse events, and safety monitoring findings.

Prioritize:

- adverse-event type, severity, frequency, and seriousness
- assessment window and event count/rate
- discontinuation or withdrawal due to adverse events
- physiological safety endpoints when central
- comparator and exposure context
- whether safety findings favor, disfavor, or are neutral for the intervention

For `safety_category`, prefer a stable family-level category when the text
supports one. Keep the concrete paper wording in `safety_event_or_measure`.
Useful category families include cardiovascular safety, respiratory safety,
serious adverse events, discontinuation due to adverse events, suicidality,
mania or hypomania risk, induced or worsened psychosis, anxiety/panic,
dissociation, flashbacks/HPPD, seizure/convulsion, serotonin syndrome,
nausea/vomiting, headache, sedation/cognitive or motor impairment, sleep
disturbance, urinary toxicity, hepatic toxicity, renal/muscle toxicity,
neurotoxicity/cytotoxicity, weight/metabolic safety, abuse/dependence liability,
and general tolerability/adverse events. Use the general category only when the
text does not identify a more specific event, organ system, or risk family.

Treat transient psychotomimetic effects as cognitive evidence. Keep actual
induction, exacerbation, or persistence of psychosis in safety.

The concrete event is the specific graph anchor and the stable family is its
parent category. When one central finding reports several clinically meaningful
events from different families, preserve separate event anchors rather than
letting the first recognized event replace the others. Seriousness,
discontinuation, frequency, and overall tolerability remain distinct safety
summary dimensions rather than substitutes for the event type.

Capture medical/psychiatric attention, duration/resolution, ascertainment
method, management, mitigation, risk factors, or subgroup context only when it
is central to the safety finding.

Use optional controlled context fields when stated: `administration_route`,
`dosing_schedule`, `session_context`, `population_model_category`, and
`study_design_category`. These are coarse filters; keep exact paper wording in
`dose_or_regimen`, `population_or_system`, and `study_design`.

Do not extract every minor side effect as a separate item unless safety or
tolerability is central to the supplied text, the event is serious, frequent,
clinically important, or the paper reports the event as a main safety result.
Group related minor events when the text only presents them as a routine table
of adverse events.

Do not convert safety events into primary therapeutic graph endpoints. Do not
extract clinical benefit, mechanistic, pharmacokinetic, or subjective-experience
results here unless the reported finding is directly framed as safety,
tolerability, abuse liability, contraindication, monitoring, or risk.

For `result_direction`, use `positive` for better safety/tolerability or fewer
harms, `negative` for increased harms or poorer tolerability,
`no_detected_effect` for no meaningful safety difference, and `mixed` for
materially divergent safety findings.
