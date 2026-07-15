from pipeline.extract.assay_family import normalize_assay_family


def test_neural_assay_families_keep_familiar_acronyms() -> None:
    examples = {
        "resting-state fMRI BOLD connectivity": "fMRI",
        "18F-FDG PET receptor occupancy": "PET",
        "99mTc-HMPAO SPECT": "SPECT",
        "EEG event-related potential P300": "EEG",
        "MEG oscillatory power": "MEG",
        "local field potential (LFP)": "LFP",
        "whole-cell patch clamp": "Electrophysiology",
        "fiber photometry GCaMP6s": "Fiber photometry",
        "two-photon calcium imaging": "Calcium imaging",
        "7T magnetic resonance spectroscopy": "MRS",
        "structural MRI": "MRI",
    }

    for raw, expected in examples.items():
        assert normalize_assay_family("", raw) == expected


def test_non_neural_assay_families_stay_stable() -> None:
    examples = {
        "radioligand competition binding": "Binding assays",
        "cAMP beta-arrestin recruitment": "Receptor activity",
        "Western blot protein expression": "Protein assays",
        "LC-MS/MS phosphoproteomics": "Proteomics",
        "qPCR mRNA expression": "Gene expression assays",
    }

    for raw, expected in examples.items():
        assert normalize_assay_family("", raw) == expected


def test_existing_and_legacy_assay_families_are_canonicalized() -> None:
    examples = {
        "Binding / affinity": "Binding assays",
        "Protein expression / proteomics": "Protein assays",
        "Immunoassay / histology": "Immunoassays",
        "Other / mixed method": "Other",
        "Other methods": "Other",
        "Protein assays": "Protein assays",
        "Gene expression assays": "Gene expression assays",
    }

    for raw, expected in examples.items():
        assert normalize_assay_family(raw, "") == expected

    assert normalize_assay_family("Imaging / connectivity", "resting-state fMRI") == "fMRI"


def test_unclassified_assays_use_the_single_other_bucket() -> None:
    assert normalize_assay_family("", "bespoke uncategorized procedure") == "Other"
    assert normalize_assay_family("Other methods", "") == "Other"
