import Foundation
public protocol NumberType: Numeric, Codable, Equatable {}
extension Int: NumberType {}
extension Double: NumberType {}
extension Float: NumberType {}

public struct Point<T: NumberType>: Codable, Equatable {
    let x: T
    let y: T

    init(x: T, y: T) {
        self.x = x
        self.y = y
    }

    func scale(sx: T, sy: T) -> Point<T> {
        return Point(x: x * sx, y: y * sy)
    }

    func translate(dx: T, dy: T) -> Point<T> {
        return Point(x: x + dx, y: y + dy)
    }

}


// Move the operator overloads outside of the struct
public func +<T: NumberType>(lhs: Point<T>, rhs: Point<T>) -> Point<T> {
    return Point(x: lhs.x + rhs.x, y: lhs.y + rhs.y)
}

public func -<T: NumberType>(lhs: Point<T>, rhs: Point<T>) -> Point<T> {
    return Point(x: lhs.x - rhs.x, y: lhs.y - rhs.y)
}