from twitcher.owsexceptions import OWSException


def test_owsexceptions_json_formatter():
    test_cases = [
        ("\nLeading new-line", "Leading new-line."),
        ("\nnew-lines\n\neverywhere\n", "New-lines. Everywhere."),
        ("Loads of new-lines\nat the end\n\n\n\n\n", "Loads of new-lines. At the end."),
        ("many new-lines\n\n\nin the middle", "Many new-lines. In the middle."),
        ("Already has dot at the end.\n", "Already has dot at the end."),
        ("\nDot only\n\n\nat the end.", "Dot only. At the end."),
        ("Loads of dots remains...\n", "Loads of dots remains..."),
    ]

    test_code = "Test Exception 1337"
    for test, expect in test_cases:
        json_body = OWSException.json_formatter(status=test_code, body=test, title="", environ={})
        assert json_body['code'] == test_code
        assert json_body['description'] == expect, \
            "Result does not match expected value" + \
            "\n  Result: `{}`".format(json_body['description']) + \
            "\n  Expect: `{}`".format(expect)