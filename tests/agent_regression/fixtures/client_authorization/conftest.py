import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def generated_test_cases():
    path = Path(
        "ready_artifacts/test_cases"
    )

    filename = list(path.glob("test_cases_*.md"))

    assert filename, "Не найдены файлы с тест-кейсами"
    return [
        file.read_text(encoding="utf-8")
        for file in filename
    ]


@pytest.fixture(scope="session")
def etalon_structure():
    return [
        "Название",
        "Приоритет",
        "Цель",
        "Источник",
        "Предусловия теста",
        "Тестовые данные",
        "Шаги"
    ]
