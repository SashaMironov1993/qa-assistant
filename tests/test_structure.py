def test_cases(generated_test_cases):
    for content in generated_test_cases:
        assert content.strip(), ("Файл с тест-кейсами пустой")


def test_structure(etalon_structure, generated_test_cases):
    for content in generated_test_cases:
        for field in etalon_structure:
            assert field in content, (f"Отсутсвует обязательноe поле {field}")





"""
TO DO:
надо бы еще написать кейс на проверку, что ожидаемые результаты не пустые, но я пока не придумал как это сделать.
"""

