from repltilian import repl_output


def assert_lines_equal(left: str, right: str) -> None:
    left = left.strip()
    right = right.strip()
    for i, (ll, rl) in enumerate(zip(left, right)):
        assert ll.strip() == rl.strip(), f"Line {i}: {ll} != {rl} are not equal"


def test__clean_prompt1() -> None:
    """Example 1.
    var point = Point<Float>(x: 1, y: 2)
    """
    repl_output_str = (
        "\x1b[1G\x1b[1G\x1b[J 63>  \r\n 64.  \x1b[1G 64. \r 64. \x1b[1G 64. \x1b["
        "6Gvar point = Point<Float>(x\r 64. var point = Point<Float>(x:\x1b[1G 64. \x1b[33G 1, "
        "y\r 64. var point = Point<Float>(x: 1, y:\x1b[1G 64. \x1b[39G 2)\x1b[1G\x1b[1G\x1b[J 64. "
        "var point = Point<Float>(x: 1, y: 2) \r\n 65.  \x1b[1G 65. \r 65. \x1b[1G 65. \x1b["
        "6G\x1b[6G\r\npoint: Point<Float> = {\r\n  x = 1\r\n  y = 2\r\n}\r\n\x1b[1G\x1b[J 65>  "
        "\x1b[1G 65> \r 65> \x1b[1G 65> \x1b[6G"
    )
    cleaned_output = repl_output.clean(repl_output_str)
    expected_output = (
        "63>  \n 64. var point = Point<Float>(x: 1, y: 2) \n 65.  \npoint: "
        "Point<Float> = {\n  x = 1\n  y = 2\n}\n 65>"
    )  # noqa: E501
    assert cleaned_output == expected_output


def test__clean_prompt2() -> None:
    """Example 2. var i = 1.0."""
    repl_output_str = (
        "var i = 1.0\x1b[18G\r\ni: Double = 1\r\n\x1b[1G\x1b[J 110>  \x1b[1G 110> "
        "\r 110> \x1b[1G 110> \x1b[7G"
    )  # noqa: E501
    cleaned_output = repl_output.clean(repl_output_str)
    expected_output = "var i = 1.0\ni: Double = 1\n 110>"
    assert cleaned_output == expected_output


def test__clean_prompt3() -> None:
    """Example 3.
    //cpp
    var point1 = Point<Float>(x: 5, y: 2)
    var point2 = Point<Float>(x: 5, y: 2)
    let result = point1 + point2 + point
    result.translate(dx: 1, dy: 100)
    """
    repl_output_str = (
        "//cpp\x1b[1G\x1b[1G\x1b[J 115> //cpp \r\n 116.  \x1b[1G 116. \r 116. \x1b[1G 116. "
        "\x1b[7Gvar point1 = Point<Float>(x\r 116. var point1 = Point<Float>(x:\x1b[1G 116. "
        "\x1b[35G 5, y\r 116. var point1 = Point<Float>(x: 5, y:\x1b[1G 116. \x1b[41G 2)\x1b["
        "1G\x1b[1G\x1b[J 116. var point1 = Point<Float>(x: 5, y: 2) \r\n 117.  \x1b[1G 117. \r "
        "117. \x1b[1G 117. \x1b[7Gvar point2 = Point<Float>(x\r 117. var point2 = Point<Float>("
        "x:\x1b[1G 117. \x1b[35G 5, y\r 117. var point2 = Point<Float>(x: 5, y:\x1b[1G 117. "
        "\x1b[41G 2)\x1b[1G\x1b[1G\x1b[J 117. var point2 = Point<Float>(x: 5, y: 2) \r\n 118.  "
        "\x1b[1G 118. \r 118. \x1b[1G 118. \x1b[7Glet result = point1 + point2 + point\x1b["
        "1G\x1b[1G\x1b[J 118. let result = point1 + point2 + point \r\n 119.  \x1b[1G 119. \r "
        "119. \x1b[1G 119. \x1b[7Gresult.translate(dx\r 119. result.translate(dx:\x1b[1G 119. "
        "\x1b[27G 1, dy\r 119. result.translate(dx: 1, dy:\x1b[1G 119. \x1b[34G 100)\x1b[1G\x1b["
        "1G\x1b[J 119. result.translate(dx: 1, dy: 100) \r\n 120.  \x1b[1G 120. \r 120. \x1b[1G "
        "120. \x1b[7G\x1b[7G\r\n$R1: Point<Float> = {\r\n  x = 12\r\n  y = 106\r\n}\r\npoint1: "
        "Point<Float> = {\r\n  x = 5\r\n  y = 2\r\n}\r\npoint2: Point<Float> = {\r\n  x = 5\r\n  y "
        "= 2\r\n}\r\nresult: Point<Float> = {\r\n  x = 11\r\n  y = 6\r\n}\r\n\x1b[1G\x1b[J 120>  "
        "\x1b[1G 120> \r 120> \x1b[1G 120> \x1b[7G"
    )
    cleaned_output = repl_output.clean(repl_output_str)
    expected_output = (
        "115> //cpp \n 116. var point1 = Point<Float>(x: 5, y: 2) \n 117. var "
        "point2 = Point<Float>(x: 5, y: 2) \n 118. let result = point1 + point2 + "
        "point \n 119. result.translate(dx: 1, dy: 100) \n 120.  \n$R1: "
        "Point<Float> = {\n  x = 12\n  y = 106\n}\npoint1: Point<Float> = {\n  x = 5\n  y = "
        "2\n}\npoint2: Point<Float> = {\n  x = 5\n  y = 2\n}\nresult: Point<Float> = {\n  x = "
        "11\n  y = 6\n}\n 120>"
    )
    assert cleaned_output == expected_output


def test__clean_prompt_with_error_in_output() -> None:
    """Example with error in output.
    //cpp
    result.error(dx: 1, dy: 100)
    """
    repl_output_str = (
        "//cpp\x1b[1G\x1b[1G\x1b[J 130> //cpp \r\n 131.  \x1b[1G 131. \r 131. \x1b["
        "1G 131. \x1b[7Gresult.error(dx\r 131. result.error(dx:\x1b[1G 131. \x1b["
        "23G 1, dy\r 131. result.error(dx: 1, dy:\x1b[1G 131. \x1b[30G 100)\x1b["
        "1G\x1b[1G\x1b[J 131. result.error(dx: 1, dy: 100) \r\n 132.  \x1b[1G 132. "
        "\r 132. \x1b[1G 132. \x1b[7G\x1b[7G\r\nerror: repl.swift:131:8: value of "
        "type 'Point<Float>' has no member 'error'\r\nresult.error(dx: 1, "
        "dy: 100)\r\n~~~~~~ ^~~~~\r\n\r\n\r\n\x1b[1G\x1b[J 130>  \x1b[1G 130> \r "
        "130> \x1b[1G 130> \x1b[7G"
    )
    cleaned_output = repl_output.clean(repl_output_str)
    expected_output = (
        "130> //cpp \n 131. result.error(dx: 1, dy: 100) \n 132.  \nerror: "
        "repl.swift:131:8: value of type 'Point<Float>' has no member "
        "'error'\nresult.error(dx: 1, dy: 100)\n~~~~~~ ^~~~~\n\n\n 130>"
    )
    assert cleaned_output == expected_output


def test__has_error() -> None:
    text = "error: repl.swift:131:8: value of type 'Point<Float>'\n 130>"
    assert repl_output.search_for_error(text) is not None

    text = "var i = 1.0\ni: Double = 1\n 110>"
    assert repl_output.search_for_error(text) is None

    text = "$E11: repl.swift:131:8: value of type 'Point<Float>'\n 130>"
    assert repl_output.search_for_error(text) is not None


def test__strip_prompt_input_lines() -> None:
    output = """
    169>
     170. var point1 = Point<Float>(x: 5, y: 2)
     174. result.translate(dx: 1, dy: 100)
     175.
    $R9: Point<Float> = {
      x = 12
      y = 106
    }
    """
    output = repl_output.remove_prompt_input_lines(output)
    expected_output = """
    $R9: Point<Float> = {
      x = 12
      y = 106
    }
    """
    assert_lines_equal(output, expected_output)


def test__strip_prompt_input_lines__no_inputs() -> None:
    output = """
    $R9: Point<Float> = {
      x = 12
      y = 106
    }
    """
    output = repl_output.remove_prompt_input_lines(output)
    expected_output = """
    $R9: Point<Float> = {
      x = 12
      y = 106
    }
    """
    assert_lines_equal(output, expected_output)


def test__find_variables() -> None:
    output = """
    169>
     170. var point1 = Point<Float>(x: 5, y: 2)
     174. result.translate(dx: 1, dy: 100)
     175. fake: String = "hello"
    pairs: [Tuple<Point, Point>] = 5 values {
    }
    a: String = "hello"
    $R9: Point<Float> = {
      x = 12
      y = 106
    }
    result: Point<Float> = {
      x = 11
      y = 6
    }
    results: [Point<Float>] = 3 values {
      [0] = {
        x = 11
        y = 6
      }
      [1] = {
        x = 5
        y = 2
      }
      [2] = {
        x = 5
        y = 2
      }
    }
    """
    variables = repl_output.find_variables(output)
    exp_variables = {
        "pairs": "[Tuple<Point, Point>]",
        "$R9": "Point<Float>",
        "a": "String",
        "result": "Point<Float>",
        "results": "[Point<Float>]",
    }
    assert len(variables) == len(exp_variables)
    for key, dtype in exp_variables.items():
        assert variables[key][0] == dtype


def test__find_variables__should_ignore_text() -> None:
    output = """
    test: will ignore this line - ok?
    warning: will ignore this line = ok?
    warning: will ignore this line=ok?
    """
    variables = repl_output.find_variables(output)
    assert variables == {}


def test__find_variables__should_parse_correctly() -> None:
    output = """
    a: String = "hello = hello"
    b: [Any] = [1, 2, 3, "hello == hello"]
    """
    variables = repl_output.find_variables(output)
    assert len(variables) == 2
    assert variables["a"] == ("String", '"hello = hello"')
    assert variables["b"] == ("[Any]", '[1, 2, 3, "hello == hello"]')


def test__batch_prompt() -> None:
    batches = repl_output.batch_prompt("let x = 1")
    assert batches == ["let x = 1"]
    prompt = """
    let x = 1
    // comment

    let y = 2
    """
    prompt = "\n".join([line.strip() for line in prompt.split("\n")])
    batches = repl_output.batch_prompt(prompt)
    assert batches == ["let x = 1\nlet y = 2"]
    batches = repl_output.batch_prompt(prompt, size=1)
    assert batches == ["let x = 1", "let y = 2"]
