#!/usr/bin/env swift

import Foundation
import NaturalLanguage

struct InputRow: Decodable {
    let doi: String
    let title: String
}

struct OutputRow: Encodable {
    let doi: String
    let detectedLanguage: String
    let confidence: Double
    let alternatives: [String: Double]
}

let decoder = JSONDecoder()
let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys]

while let line = readLine() {
    guard let data = line.data(using: .utf8),
          let row = try? decoder.decode(InputRow.self, from: data) else {
        continue
    }
    let recognizer = NLLanguageRecognizer()
    recognizer.processString(row.title)
    let hypotheses = recognizer.languageHypotheses(withMaximum: 3)
    let dominant = recognizer.dominantLanguage?.rawValue ?? ""
    let confidence = hypotheses.first(where: { $0.key.rawValue == dominant })?.value ?? 0.0
    let alternatives = Dictionary(uniqueKeysWithValues: hypotheses.map { ($0.key.rawValue, $0.value) })
    let output = OutputRow(
        doi: row.doi,
        detectedLanguage: dominant,
        confidence: confidence,
        alternatives: alternatives
    )
    if let encoded = try? encoder.encode(output),
       let text = String(data: encoded, encoding: .utf8) {
        print(text)
    }
}
