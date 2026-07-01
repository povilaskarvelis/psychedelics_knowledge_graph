from pipeline.extract.mechanistic_assay_family import normalize_mechanistic_assay_family


def test_neural_assay_families_keep_familiar_acronyms() -> None:
    examples = {
        "resting-state fMRI BOLD connectivity": "fMRI",
        "18F-FDG PET receptor occupancy": "PET / SPECT",
        "EEG event-related potential P300": "EEG",
        "MEG oscillatory power": "MEG",
        "local field potential (LFP)": "LFP / electrophysiology",
        "fiber photometry GCaMP6s": "Calcium imaging / photometry",
        "7T magnetic resonance spectroscopy": "MRI / MRS",
    }

    for raw, expected in examples.items():
        assert normalize_mechanistic_assay_family("", raw) == expected


def test_non_neural_assay_families_stay_stable() -> None:
    examples = {
        "radioligand competition binding": "Binding / affinity",
        "cAMP beta-arrestin recruitment": "Receptor activity",
        "Western blot protein expression": "Protein expression / proteomics",
        "qPCR mRNA expression": "Gene expression",
    }

    for raw, expected in examples.items():
        assert normalize_mechanistic_assay_family("", raw) == expected
