INIT_COMMANDS = """
import Foundation

// Function to deserialize an object from a JSON file at the given path
func _deserializeObject<T: Decodable>(_ path: String) throws -> T {
    let url = URL(fileURLWithPath: path)
    let data = try Data(contentsOf: url)
    let decoder = JSONDecoder()
    let object = try decoder.decode(T.self, from: data)
    return object
}

// Function to serialize an object and save it as a JSON file at the given path
func _serializeObject<T: Encodable>(_ object: T, to path: String) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys] // Optional formatting
    let data = try encoder.encode(object)
    let url = URL(fileURLWithPath: path)
    try data.write(to: url)
}

"""
END_OF_INCLUDE = "// -- END OF AUTO REPL INCLUDE --"
