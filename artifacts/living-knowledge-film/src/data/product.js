// Real numbers from psychedelicskg.com (release of 2026-09-17, read 2026-09-28), used by Act III's stylized views.

export const STATS = {total: 21735, primary: 16731, reviews: 4672, meta: 332};

// Analyze · Publication history (2000–2026): primary studies, reviews, meta-analyses per year
export const PUB_HISTORY = [
  [2000, 161, 17, 0], [2001, 169, 22, 0], [2002, 165, 28, 0], [2003, 186, 22, 1], [2004, 204, 26, 0], [2005, 260, 15, 1],
  [2006, 233, 32, 1], [2007, 249, 28, 2], [2008, 303, 31, 0], [2009, 260, 33, 1], [2010, 301, 36, 2], [2011, 341, 46, 1],
  [2012, 335, 53, 2], [2013, 385, 90, 1], [2014, 385, 80, 3], [2015, 423, 97, 9], [2016, 449, 90, 9], [2017, 484, 112, 5],
  [2018, 545, 135, 3], [2019, 598, 141, 10], [2020, 713, 188, 23], [2021, 711, 262, 24], [2022, 815, 334, 22],
  [2023, 922, 363, 28], [2024, 1037, 442, 64], [2025, 1206, 554, 46], [2026, 965, 428, 48],
];

// research areas, in the site's order and palette; papers per area for primary studies, meta-analyses and reviews
export const AREAS = [
  {name: 'Conditions', color: '#708aa7', primary: 2001, meta: 152, reviews: 1725, all: 3878},
  {name: 'Safety', color: '#b89a5b', primary: 4072, meta: 114, reviews: 1393, all: 5579},
  {name: 'Cognition', color: '#a96f7e', primary: 2046, meta: 23, reviews: 143, all: 2212},
  {name: 'Behavior', color: '#69a196', primary: 2344, meta: 5, reviews: 62, all: 2411},
  {name: 'Subjective effects', color: '#b98278', primary: 1564, meta: 9, reviews: 211, all: 1784},
  {name: 'Treatment context', color: '#7e72a1', primary: 862, meta: 5, reviews: 132, all: 999},
  {name: 'Real-world use', color: '#9f9872', primary: 3707, meta: 9, reviews: 184, all: 3900},
  {name: 'Brain regions', color: '#719d96', primary: 1446, meta: 9, reviews: 171, all: 1626},
  {name: 'Molecular effects', color: '#9c8670', primary: 3599, meta: 8, reviews: 604, all: 4211},
  {name: 'Targets', color: '#70819a', primary: 1928, meta: 2, reviews: 879, all: 2809},
];
export const EVIDENCE_TOTALS = {primary: 12805, meta: 306, reviews: 3710}; // 2000–2026

// Analyze · Cross-domain overlap (papers shared by two research areas), lower triangle incl. diagonal, AREAS order
export const OVERLAP = [
  [4170],
  [1827, 5799],
  [248, 507, 2275],
  [136, 463, 734, 2472],
  [440, 644, 361, 162, 1854],
  [417, 292, 72, 45, 403, 1069],
  [395, 1045, 257, 189, 426, 323, 4038],
  [224, 255, 356, 336, 152, 15, 49, 1667],
  [483, 1232, 772, 1160, 137, 13, 73, 814, 4390],
  [483, 718, 349, 656, 137, 17, 48, 429, 1101, 3001],
];

// Analyze · Literature by entity (2000–2026)
export const TOP_COMPOUNDS = [['Ketamine', 6176], ['MDMA', 3993], ['Psilocybin', 2008], ['LSD', 1238], ['S-ketamine', 1145], ['Ayahuasca', 648], ['DMT', 507]];

// Explore · Psilocybin (primary studies)
export const PSILO = {
  tooltip: {studies: 263, findings: 599, connections: 35},
  studies: 271, open: 209,
  perYear: [[2014, 1.9], [2015, 3.8], [2016, 7.7], [2017, 11.5], [2018, 21.1], [2019, 3.8], [2020, 13.4], [2021, 7.7], [2022, 28.8], [2023, 46.1], [2024, 71], [2025, 96], [2026, 88.3]],
  dosing: [['Repeated dosing', 82], ['Single-dose session', 81], ['Microdosing', 7], ['Dose-ranging', 5]],
  context: [['Therapy-assisted session', 118], ['Naturalistic use', 43], ['Clinical administration', 28], ['Ceremony & retreat', 9]],
  designs: [['RCT', 57], ['Open-label trial', 46], ['Qualitative', 39], ['Observational study', 32], ['Case report', 17]],
  conditions: ['Major depressive disorder', 'Treatment-resistant depression', 'Distress in life-threatening illness', 'Alcohol use disorder',
    'Obsessive-compulsive disorder', 'Suicidal ideation & behavior', 'Post-traumatic stress disorder', 'Tobacco use disorder', 'Anorexia nervosa',
    'Cluster headache', 'Bipolar disorder', 'Eating disorders', 'Substance use disorder', 'ADHD', 'Demoralization', 'Bipolar II disorder',
    'Body dysmorphic disorder', 'Methamphetamine use disorder', 'Migraine', 'Opioid use disorder'],
};

// Explore · a finding card (the structure every paper is read into)
export const CARD = {
  title: 'Psilocybin → Major depressive disorder',
  design: 'Observational study',
  finding: 'Treatment was associated with significant reductions in maladaptive emotion regulation strategies, specifically catastrophizing, self-blame, and rumination.',
  fields: [
    ['Exact exposure', 'LSD or psilocybin', 'context'],
    ['Population', 'Participants with treatment-resistant depression or anxiety', 'context'],
    ['Sample', '67', 'method'],
    ['Timepoint', '1–3 months post-treatment', 'method'],
    ['Administration', '100 µg LSD or 25 mg psilocybin · oral', 'method'],
  ],
  source: 'Aboulafia-Brakha et al. (2026) · Psychiatry Research',
};

// MCP session against the live server (results as of the 2026-09-17 release)
export const AGENT = {ptsd: 469, relationships: 513, top: [['MDMA', 252], ['Ketamine', 151], ['Psilocybin', 30]]};

// Explore · Psilocybin → Major depressive disorder (primary studies): one compound–condition pair
export const EDGE = {
  title: 'Psilocybin → Major depressive disorder', studies: 75, open: 56,
  perYear: [[2019, 14.8], [2020, 14.8], [2021, 14.8], [2022, 59.1], [2023, 59.1], [2024, 73.8], [2025, 96], [2026, 81.2]],
  designs: [['RCT', 30], ['Open-label trial', 6], ['Observational study', 5], ['Qualitative', 5], ['Follow-up study', 4]],
};
// its findings, as the explorer lists them (finding, study design, source)
export const FINDINGS = [
  ['Observational study', 'Treatment was associated with significant reductions in maladaptive emotion regulation strategies, specifically catastrophizing, self-blame, and rumination.', 'Aboulafia-Brakha et al. (2026) · Psychiatry Research'],
  ['Qualitative', 'Microdosing was reported to alleviate or entirely cure depression, including long-standing major depression and treatment-resistant cases.', 'Andersson & Kjellgren (2019) · Harm Reduction Journal'],
  ['RCT', 'Psilocybin treatment resulted in a rapid and significant reduction in depressive symptoms by day 8 compared to the niacin group.', 'Raison et al. (2023) · JAMA'],
  ['RCT', 'Between-group differences in depressive symptoms were no longer significant at the 1-year follow-up.', 'Yngwe et al. (2026) · JAMA Network Open'],
  ['Observational study', 'Patients showed a significant reduction in depressive symptoms immediately following the psychedelic-assisted therapy session.', 'Calder et al. (2024) · Journal of Psychopharmacology'],
  ['RCT', 'Psilocybin treatment was associated with significantly reduced functional disability scores compared with niacin at day 43.', 'Raison et al. (2023) · JAMA'],
  ['RCT', 'At day 42, the remission rate was significantly higher in the psilocybin group compared to the niacin group.', 'Yngwe et al. (2026) · JAMA Network Open'],
];
export const HERO_FINDING = 2; // the one we open
export const HERO_CARD = {
  title: 'Psilocybin → Major depressive disorder', design: 'RCT',
  finding: 'Psilocybin treatment resulted in a rapid and significant reduction in depressive symptoms by day 8 compared to the niacin group.',
  fields: [
    ['Population', 'Adults aged 21 to 65 with moderate or greater symptom severity', 'context'],
    ['Sample', '104', 'method'],
    ['Timepoint', 'Day 8', 'method'],
    ['Comparator', 'Active placebo (niacin)', 'method'],
    ['Administration', 'Single 25 mg oral dose with psychological support', 'context'],
  ],
  paper: {title: 'Single-Dose Psilocybin Treatment for Major Depressive Disorder: A Randomized Clinical Trial',
    authors: 'Charles L. Raison, Gerard Sanacora, Joshua Woolley, et al.', journal: 'JAMA', year: 2023, doi: '10.1001/jama.2023.14530', more: 3},
};

// Analyze · the whole field at a glance (release of 2026-09-17, read 2026-09-29). Three views of the Analyze page: the
// publication history above (PUB_HISTORY, re-read on the live site 2026-10-30), coverage and gaps.

// Coverage — who or what was studied, per compound: primary studies by population or model (Evidence coverage: rows
// Compound, columns Population / model, all research areas, 2000–2026, read 2026-09-29). Papers per cell; "other" folds in
// the site's Other, In silico, Mixed and Not recorded columns.
export const POPULATIONS = {
  groups: [['Human participants', '#7fd6cb'], ['Preclinical animals', '#e6b765'], ['Cell & tissue', '#ae9df3'], ['Other', '#5b6569']],
  compounds: [
    ['Ketamine', [2510, 1809, 318, 349 + 36 + 5 + 4]],
    ['S-ketamine', [608, 189, 60, 39 + 12 + 1 + 1]],
    ['Psilocybin', [1057, 190, 58, 157 + 17 + 1]],
    ['MDMA', [2148, 913, 191, 469 + 10 + 3 + 3]],
    ['LSD', [812, 151, 98, 134 + 14 + 2]],
    ['Ayahuasca', [440, 41, 11, 111 + 1 + 1]],
  ],
};

// Analyze · Evidence coverage within the Conditions research area (2000–2026), rows = topic, columns = compound: papers per
// condition × compound, for primary studies and for the same view with Papers set to Meta-analyses (read 2026-09-28).
// Opioid use disorder and cluster headache have no meta-analyses in the release.
export const COVERAGE = {
  compounds: ['Ketamine', 'S-ketamine', 'Psilocybin', 'MDMA', 'LSD', 'Ayahuasca', 'Ibogaine', 'DMT'],
  rows: [ // condition, primary studies per compound, meta-analyses per compound
    ['Treatment-resistant depression', [359, 246, 42, 0, 0, 8, 0, 4], [28, 23, 8, 0, 0, 2, 0, 0]],
    ['Major depressive disorder', [367, 77, 76, 9, 17, 8, 4, 3], [30, 13, 8, 1, 1, 1, 0, 0]],
    ['Suicidal ideation & behavior', [244, 87, 23, 9, 6, 5, 1, 3], [18, 11, 1, 0, 0, 0, 0, 0]],
    ['Post-traumatic stress disorder', [81, 13, 19, 58, 10, 5, 5, 3], [8, 0, 3, 14, 1, 1, 0, 0]],
    ['Alcohol use disorder', [13, 2, 19, 6, 2, 5, 3, 0], [0, 0, 1, 1, 3, 1, 0, 0]],
    ['Substance use disorder', [12, 0, 10, 9, 6, 24, 9, 2], [3, 0, 3, 0, 2, 0, 1, 1]],
    ['Opioid use disorder', [14, 1, 4, 1, 2, 1, 14, 0], [0, 0, 0, 0, 0, 0, 0, 0]],
    ['Obsessive-compulsive disorder', [19, 6, 15, 7, 2, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0]],
    ['Distress in life-threatening illness', [1, 1, 26, 2, 5, 1, 0, 0], [0, 0, 3, 1, 0, 0, 0, 0]],
    ['Cluster headache', [5, 0, 14, 0, 7, 0, 0, 1], [0, 0, 0, 0, 0, 0, 0, 0]],
  ],
};
