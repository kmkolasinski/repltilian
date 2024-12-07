import Foundation

public protocol NumberType: Numeric, Codable, Equatable {}

// Extend the NumberType protocol to conform to FloatingPoint for sqrt
extension Float: NumberType {}
extension Double: NumberType {}

public struct Point<T: NumberType>: Codable, Equatable {
    let x: T
    let y: T

    init(x: T, y: T) {
        self.x = x
        self.y = y
    }

    func scale(sx: T, sy: T) -> Point<T> {
        Point(x: x * sx, y: y * sy)
    }

    func translate(dx: T, dy: T) -> Point<T> {
        return Point(x: x + dx, y: y + dy)
    }
}

// Define Neighbor and SearchResult structures
public struct Neighbor<T: NumberType>: Codable, Equatable {
    let point: Point<T>
    let distance: T
}

public struct SearchResult<T: NumberType>: Codable, Equatable {
    let queryPoint: Point<T>
    let neighbors: [Neighbor<T>]
}

func findKNearestNeighbors<T: FloatingPoint>(query: [Point<T>], dataset: [Point<T>], k: Int = 5)
    -> [SearchResult<T>]
{
    var results: [SearchResult<T>] = []

    for queryPoint in query {
        var distances: [Neighbor<T>] = []

        // Calculate distances to all dataPoints {
        for dataPoint in dataset {
            let dx = queryPoint.x - dataPoint.x
            let dy = queryPoint.y - dataPoint.y
            let distance = (dx * dx + dy * dy).squareRoot()
            distances.append(Neighbor(point: dataPoint, distance: distance))
        }

        // Sort neighbors by distance
        distances.sort { $0.distance < $1.distance }

        // Select the first k neighbors
        let kNeighbors = Array(distances.prefix(k))

        // Add to results
        let searchResult = SearchResult(queryPoint: queryPoint, neighbors: kNeighbors)
        results.append(searchResult)
    }

    return results
}

// Operator overloads for Point
public func + <T: NumberType>(lhs: Point<T>, rhs: Point<T>) -> Point<T> {
    return Point(x: lhs.x + rhs.x, y: lhs.y + rhs.y)
}

public func - <T: NumberType>(lhs: Point<T>, rhs: Point<T>) -> Point<T> {
    return Point(x: lhs.x - rhs.x, y: lhs.y - rhs.y)
}

func removeBrackets(from text: String) -> String {
    let brackets = ["[", "]"]
    return text.filter { !brackets.contains(String($0)) }
}
