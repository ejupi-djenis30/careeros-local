from backend.ai.evaluation import load_dataset
from backend.ai.task_specs import TASK_SPECS


def test_golden_dataset_is_versioned_synthetic_and_covers_every_task() -> None:
    dataset = load_dataset()

    assert dataset.synthetic_only is True
    assert dataset.dataset_version == "1.0.0"
    assert {case.task_id for case in dataset.cases} == set(TASK_SPECS)


def test_every_golden_output_satisfies_its_versioned_contract() -> None:
    dataset = load_dataset()

    for case in dataset.cases:
        output = TASK_SPECS[case.task_id].output_model.model_validate(case.expected_output)
        assert output.model_dump(mode="json")
