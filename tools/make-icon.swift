#!/usr/bin/env swift
// Draws the app icon and writes macos/ClaudeUsage.icns.
// Run from the repo root: swift tools/make-icon.swift

import AppKit
import ImageIO
import UniformTypeIdentifiers

// Three stacked usage bars on a dark plate, in the palette the widget's "zellij"
// theme uses: the fill walks green -> yellow -> red as the budget burns, so the
// icon says at a glance what the app measures. Every measure is a fraction of
// the icon side, so it is drawn fresh at each size instead of being scaled down.
func drawIcon(side S: CGFloat, into ctx: CGContext) {
    let margin = S * 0.0977                     // Apple's icon grid: 824 pt of art in 1024
    let box = CGRect(x: margin, y: margin, width: S - 2 * margin, height: S - 2 * margin)
    let radius = box.width * 0.225

    func rgb(_ hex: UInt32) -> NSColor {
        NSColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
                green: CGFloat((hex >> 8) & 0xFF) / 255,
                blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }

    // Plate: the ghostty ground, lifted slightly at the top so the icon has a
    // light source rather than reading as a flat sticker.
    ctx.saveGState()
    ctx.addPath(CGPath(roundedRect: box, cornerWidth: radius, cornerHeight: radius, transform: nil))
    ctx.clip()
    let plate = CGGradient(
        colorsSpace: CGColorSpaceCreateDeviceRGB(),
        colors: [rgb(0x24262F).cgColor, rgb(0x14151B).cgColor] as CFArray,
        locations: [0, 1])!
    ctx.drawLinearGradient(plate,
                           start: CGPoint(x: box.midX, y: box.maxY),
                           end: CGPoint(x: box.midX, y: box.minY),
                           options: [])
    ctx.restoreGState()

    // Hairline rim: separates the plate from a dark wallpaper without a border.
    ctx.saveGState()
    ctx.addPath(CGPath(roundedRect: box.insetBy(dx: S * 0.004, dy: S * 0.004),
                       cornerWidth: radius, cornerHeight: radius, transform: nil))
    ctx.setStrokeColor(rgb(0x6272A4).withAlphaComponent(0.35).cgColor)
    ctx.setLineWidth(S * 0.008)
    ctx.strokePath()
    ctx.restoreGState()

    // Bars. Fractions are deliberately unequal — a row of identical bars reads
    // as a hamburger menu at 32 pt.
    let bars: [(fill: CGFloat, color: UInt32)] = [
        (0.86, 0xFF5555),   // red, past the 80% mark
        (0.58, 0xF1FA8C),   // yellow, the middle band
        (0.31, 0x50FA7B),   // green, plenty left
    ]
    let inset = box.width * 0.155
    let trackW = box.width - 2 * inset
    let barH = box.height * 0.118
    let gap = box.height * 0.105
    let stack = CGFloat(bars.count) * barH + CGFloat(bars.count - 1) * gap
    var y = box.midY + stack / 2 - barH

    for bar in bars {
        let track = CGRect(x: box.minX + inset, y: y, width: trackW, height: barH)
        ctx.setFillColor(rgb(0x6272A4).withAlphaComponent(0.30).cgColor)
        ctx.addPath(CGPath(roundedRect: track, cornerWidth: barH / 2, cornerHeight: barH / 2, transform: nil))
        ctx.fillPath()

        // A fill shorter than its own cap would render as a lozenge, so clamp.
        let w = max(barH, trackW * bar.fill)
        let fill = CGRect(x: track.minX, y: y, width: w, height: barH)
        ctx.setFillColor(rgb(bar.color).cgColor)
        ctx.addPath(CGPath(roundedRect: fill, cornerWidth: barH / 2, cornerHeight: barH / 2, transform: nil))
        ctx.fillPath()

        y -= barH + gap
    }
}

func image(side: Int) -> CGImage {
    let S = CGFloat(side)
    let ctx = CGContext(data: nil, width: side, height: side, bitsPerComponent: 8,
                        bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.setAllowsAntialiasing(true)
    drawIcon(side: S, into: ctx)
    return ctx.makeImage()!
}

// iconutil wants a .iconset directory of the ten canonical sizes.
let root = FileManager.default.currentDirectoryPath
let iconset = URL(fileURLWithPath: root).appendingPathComponent("build/ClaudeUsage.iconset")
try? FileManager.default.removeItem(at: iconset)
try! FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)

let sizes: [(name: String, px: Int)] = [
    ("icon_16x16", 16), ("icon_16x16@2x", 32),
    ("icon_32x32", 32), ("icon_32x32@2x", 64),
    ("icon_128x128", 128), ("icon_128x128@2x", 256),
    ("icon_256x256", 256), ("icon_256x256@2x", 512),
    ("icon_512x512", 512), ("icon_512x512@2x", 1024),
]

for (name, px) in sizes {
    let url = iconset.appendingPathComponent("\(name).png")
    let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, image(side: px), nil)
    CGImageDestinationFinalize(dest)
}

let out = URL(fileURLWithPath: root).appendingPathComponent("macos/ClaudeUsage.icns")
let p = Process()
p.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
p.arguments = ["-c", "icns", iconset.path, "-o", out.path]
try! p.run()
p.waitUntilExit()
print(p.terminationStatus == 0 ? "wrote \(out.path)" : "iconutil failed")
