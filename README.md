# repltilian

[![codecov](https://codecov.io/gh/kmkolasinski/repltilian/branch/main/graph/badge.svg?token=repltilian_token_here)](https://codecov.io/gh/kmkolasinski/repltilian)
[![CI](https://github.com/kmkolasinski/repltilian/actions/workflows/main.yml/badge.svg)](https://github.com/kmkolasinski/repltilian/actions/workflows/main.yml)

Interactive Swift REPL wrapper for Python

# Install it from PyPI
https://pypi.org/project/repltilian/
```bash
pip install repltilian
```

# Basic Usage

See notebook [demo.ipynb](notebooks/demo.ipynb)

```py
from repltilian import SwiftREPL
# Create a new Swift REPL process
repl = SwiftREPL()
# Run some code in the Swift REPL
repl.run("var values = [1, 2, 3, 4, 5]")
# Get the value of a variable from Swift to Python
assert repl.vars["values"].get() == [1, 2, 3, 4, 5]
# Create or update variable
repl.vars.set("values", "Array<Int>", list(range(1000)))
# Run some more code again
repl.run("""
let offset = -1
let newValues = values.map { $0 * $0 + offset}
""")
assert repl.vars["newValues"].get()[:5] == [-1, 0, 3, 8, 15]
repl.close()
```

## Auto reload file content

```py
from repltilian import SwiftREPL
# Create a new Swift REPL process
repl = SwiftREPL()
# Add a file to the REPL that will be reloaded on every run
repl.add_reload_file("demo.swift")

repl.run("""
var p1 = Point<Float>(x: 1, y: 2)
var p2 = Point<Float>(x: 2, y: 1)
var p3 = p1 + p2
""", autoreload=True)
assert repl.vars["p3"].get() == {'x': 3, 'y': 3}
```

# Basic support for ipython magic commands

See notebook [demo-magics.ipynb](notebooks/demo-magics.ipynb)

```bash
# LOAD AND INIT REPL
%load_ext repltilian
%repl_init optional/path/to/package
-----------------------------------------
# RUNNING CODE IN THE CELL
-----------------------------------------
# run swift code in the current cell
%%repl
var values = [1, 2, 3, 4, 5]
-----------------------------------------
# add file to autoreload
%repl_add_file demo.swift
-----------------------------------------
# run cell
%%repl --autoreload --verbose
var p1 = Point<Float>(x: 1, y: 2)
var p2 = Point<Float>(x: 2, y: 1)
var p3 = p1 + p2

-----------------------------------------
# GETTING AND SETTING VARIABLES
-----------------------------------------
# get the value of a variable from Swift to Python
values = %repl_get values
# set the value of a variable from Python to Swift
%repl_set values: Array<Int> = [1, 2, 3, 4, 5]
# to set the values of complex type use json.dumps to serialize the data to string
import json
data = json.dumps([1, 2, 3, 4, 5])
%repl_set values: Array<Int> = $data
```


## Line Profiling

```py
from repltilian import SwiftREPL
repl = SwiftREPL()
repl.add_reload_file("demo.swift")
# Run any command to import demo.swift code
repl.run("", autoreload=True)
repl.vars.set("query", "Array<Point<Float>>", [{'x': -1.5, 'y': -1.2}]*100)
repl.vars.set("dataset", "Array<Point<Float>>", [{'x': -1.5, 'y': -1.2}]*5000)

repl.options.output_hide_variables = True
repl.run("""
let newResult = findKNearestNeighbors(query: query, dataset: dataset, k: 10)
""")
assert len(repl.vars["newResult"].get()) == 100
assert len(repl.vars["newResult"].get()[0]) == 10

# run line profiling on the function findKNearestNeighbors
repl.options.output_hide_variables = True
repl.line_profile(
"""
let newResult = findKNearestNeighbors(query: query, dataset: dataset, k: 10)
""",
function_name="findKNearestNeighbors",
source_path="demo.swift"
)
repl.close()
```
Expected output:
```
Timer unit: 1 ns
Total time: 0.561 s
Function: findKNearestNeighbors at line 38
Line #      Hits         Time   Per Hit   % Time  Line Contents
===============================================================
     0          1     0.000000  0.000000      0.0%      var results: [SearchResult<T>] = []
     1          1     0.560541  0.560541    100.0%      for queryPoint in query {
     2        100     0.000006  0.000000      0.0%          var distances: [Neighbor<T>] = []
     3        100     0.000002  0.000000      0.0%          // Calculate distances to all dataPoints {
     4        100     0.517329  0.005173     92.3%          for dataPoint in dataset {
     5     500000     0.013336  0.000000      2.4%              let dx = queryPoint.x - dataPoint.x
     6     500000     0.010027  0.000000      1.8%              let dy = queryPoint.y - dataPoint.y
     7     500000     0.012375  0.000000      2.2%              let distance = (dx * dx + dy * dy).squareRoot()
     8     500000     0.042148  0.000000      7.5%              distances.append(Neighbor(point: dataPoint, distance: distance))
     9          0     0.000000  0.000000      0.0%          }
    10        100     0.000003  0.000000      0.0%          // Sort neighbors by distance
    11        100     0.042651  0.000427      7.6%          distances.sort { $0.distance < $1.distance }
    12        100     0.000002  0.000000      0.0%          // Select the first k neighbors
    13        100     0.000195  0.000002      0.0%          let kNeighbors = Array(distances.prefix(k))
    14        100     0.000002  0.000000      0.0%          // Add to results
    15        100     0.000021  0.000000      0.0%          let searchResult = SearchResult(queryPoint: queryPoint, neighbors: kNeighbors)
    16        100     0.000020  0.000000      0.0%          results.append(searchResult)
    17          0     0.000000  0.000000      0.0%      }
```
