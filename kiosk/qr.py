"""Generateur de QR code sans dependance externe.

Mode octet uniquement, niveaux de correction L et M, versions 1 a 10.
C'est largement suffisant pour encoder une URL de reseau local.
"""

from __future__ import annotations

# (ec_par_bloc, nb_blocs_g1, mots_donnees_g1, nb_blocs_g2, mots_donnees_g2)
_EC_TABLE = {
    (1, "L"): (7, 1, 19, 0, 0),
    (1, "M"): (10, 1, 16, 0, 0),
    (2, "L"): (10, 1, 34, 0, 0),
    (2, "M"): (16, 1, 28, 0, 0),
    (3, "L"): (15, 1, 55, 0, 0),
    (3, "M"): (26, 1, 44, 0, 0),
    (4, "L"): (20, 1, 80, 0, 0),
    (4, "M"): (18, 2, 32, 0, 0),
    (5, "L"): (26, 1, 108, 0, 0),
    (5, "M"): (24, 2, 43, 0, 0),
    (6, "L"): (18, 2, 68, 0, 0),
    (6, "M"): (16, 4, 27, 0, 0),
    (7, "L"): (20, 2, 78, 0, 0),
    (7, "M"): (18, 4, 31, 0, 0),
    (8, "L"): (24, 2, 97, 0, 0),
    (8, "M"): (22, 2, 38, 2, 39),
    (9, "L"): (30, 2, 116, 0, 0),
    (9, "M"): (22, 3, 36, 2, 37),
    (10, "L"): (18, 2, 68, 2, 69),
    (10, "M"): (26, 4, 43, 1, 44),
}

_ALIGNMENT_CENTERS = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
}

_EC_INDICATOR = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}

_MAX_VERSION = 10


class QRError(ValueError):
    """Donnees impossibles a encoder avec les versions supportees."""


# --- Arithmetique dans GF(256) -------------------------------------------------

_EXP = [0] * 512
_LOG = [0] * 256


def _init_tables() -> None:
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_tables()


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _generator_poly(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _gf_mul(coef, _EXP[i])
        poly = nxt
    return poly


def _ec_codewords(data: list[int], count: int) -> list[int]:
    gen = _generator_poly(count)
    remainder = list(data) + [0] * count
    for i in range(len(data)):
        factor = remainder[i]
        if factor == 0:
            continue
        for j, coef in enumerate(gen):
            remainder[i + j] ^= _gf_mul(coef, factor)
    return remainder[len(data):]


# --- Encodage des donnees ------------------------------------------------------


def _capacity(version: int, ec_level: str) -> int:
    ec_per_block, g1, d1, g2, d2 = _EC_TABLE[(version, ec_level)]
    return g1 * d1 + g2 * d2


def _pick_version(length: int, ec_level: str) -> int:
    for version in range(1, _MAX_VERSION + 1):
        count_bits = 8 if version < 10 else 16
        needed = (4 + count_bits + length * 8 + 7) // 8
        if needed <= _capacity(version, ec_level):
            return version
    raise QRError(
        f"{length} octets ne tiennent pas dans un QR version {_MAX_VERSION} "
        f"niveau {ec_level}"
    )


def _build_codewords(data: bytes, version: int, ec_level: str) -> list[int]:
    bits: list[int] = []

    def push(value: int, width: int) -> None:
        for i in range(width - 1, -1, -1):
            bits.append((value >> i) & 1)

    count_bits = 8 if version < 10 else 16
    push(0b0100, 4)
    push(len(data), count_bits)
    for byte in data:
        push(byte, 8)

    total = _capacity(version, ec_level) * 8
    push(0, min(4, total - len(bits)))
    if len(bits) % 8:
        push(0, 8 - len(bits) % 8)

    codewords = [int("".join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    for pad in _pad_sequence(_capacity(version, ec_level) - len(codewords)):
        codewords.append(pad)
    return codewords


def _pad_sequence(count: int) -> list[int]:
    return [0xEC if i % 2 == 0 else 0x11 for i in range(count)]


def _interleave(codewords: list[int], version: int, ec_level: str) -> list[int]:
    ec_per_block, g1, d1, g2, d2 = _EC_TABLE[(version, ec_level)]

    blocks: list[list[int]] = []
    offset = 0
    for _ in range(g1):
        blocks.append(codewords[offset:offset + d1])
        offset += d1
    for _ in range(g2):
        blocks.append(codewords[offset:offset + d2])
        offset += d2

    ec_blocks = [_ec_codewords(block, ec_per_block) for block in blocks]

    result: list[int] = []
    for i in range(max(len(b) for b in blocks)):
        for block in blocks:
            if i < len(block):
                result.append(block[i])
    for i in range(ec_per_block):
        for block in ec_blocks:
            result.append(block[i])
    return result


# --- Construction de la matrice ------------------------------------------------


class _Matrix:
    def __init__(self, size: int) -> None:
        self.size = size
        self.modules: list[list[int]] = [[0] * size for _ in range(size)]
        self.reserved: list[list[bool]] = [[False] * size for _ in range(size)]

    def set(self, row: int, col: int, value: int, reserve: bool = True) -> None:
        self.modules[row][col] = value
        if reserve:
            self.reserved[row][col] = True


def _place_finder(matrix: _Matrix, row: int, col: int) -> None:
    for r in range(-1, 8):
        for c in range(-1, 8):
            rr, cc = row + r, col + c
            if not (0 <= rr < matrix.size and 0 <= cc < matrix.size):
                continue
            border = r in (0, 6) and 0 <= c <= 6
            side = c in (0, 6) and 0 <= r <= 6
            core = 2 <= r <= 4 and 2 <= c <= 4
            matrix.set(rr, cc, 1 if (border or side or core) else 0)


def _place_alignment(matrix: _Matrix, version: int) -> None:
    centers = _ALIGNMENT_CENTERS[version]
    last = matrix.size - 7  # les motifs a ces centres chevauchent les marqueurs de position
    for row in centers:
        for col in centers:
            if (row, col) in ((6, 6), (6, last), (last, 6)):
                continue
            for r in range(-2, 3):
                for c in range(-2, 3):
                    edge = max(abs(r), abs(c))
                    matrix.set(row + r, col + c, 1 if edge != 1 else 0)


def _place_timing(matrix: _Matrix) -> None:
    for i in range(8, matrix.size - 8):
        value = 1 if i % 2 == 0 else 0
        matrix.set(6, i, value)
        matrix.set(i, 6, value)


def _reserve_format(matrix: _Matrix, version: int) -> None:
    size = matrix.size
    for i in range(9):
        if i != 6:
            matrix.set(8, i, 0)
            matrix.set(i, 8, 0)
    for i in range(8):
        matrix.set(8, size - 1 - i, 0)
        matrix.set(size - 1 - i, 8, 0)
    matrix.set(size - 8, 8, 1)  # module noir obligatoire

    if version >= 7:
        for i in range(6):
            for j in range(3):
                matrix.set(size - 11 + j, i, 0)
                matrix.set(i, size - 11 + j, 0)


def _format_bits(ec_level: str, mask: int) -> int:
    data = (_EC_INDICATOR[ec_level] << 3) | mask
    value = data << 10
    for _ in range(5):
        if value.bit_length() < 11:
            break
        value ^= 0b10100110111 << (value.bit_length() - 11)
    return ((data << 10) | value) ^ 0b101010000010010


def _version_bits(version: int) -> int:
    value = version << 12
    for _ in range(6):
        if value.bit_length() < 13:
            break
        value ^= 0b1111100100101 << (value.bit_length() - 13)
    return (version << 12) | value


def _apply_format(matrix: _Matrix, ec_level: str, mask: int) -> None:
    bits = _format_bits(ec_level, mask)
    size = matrix.size
    for i in range(15):
        bit = (bits >> i) & 1
        if i < 6:
            matrix.set(i, 8, bit)
        elif i == 6:
            matrix.set(7, 8, bit)
        elif i == 7:
            matrix.set(8, 8, bit)
        elif i == 8:
            matrix.set(8, 7, bit)
        else:
            matrix.set(8, 14 - i, bit)

        if i < 8:
            matrix.set(8, size - 1 - i, bit)
        else:
            matrix.set(size - 15 + i, 8, bit)


def _apply_version(matrix: _Matrix, version: int) -> None:
    if version < 7:
        return
    bits = _version_bits(version)
    size = matrix.size
    for i in range(18):
        bit = (bits >> i) & 1
        row, col = i // 3, i % 3
        matrix.set(size - 11 + col, row, bit)
        matrix.set(row, size - 11 + col, bit)


def _mask_condition(mask: int, row: int, col: int) -> bool:
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _place_data(matrix: _Matrix, data: list[int], mask: int) -> None:
    bits = [(byte >> i) & 1 for byte in data for i in range(7, -1, -1)]
    size = matrix.size
    index = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:  # la colonne de timing est sautee
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for offset in (0, 1):
                c = col - offset
                if matrix.reserved[row][c]:
                    continue
                bit = bits[index] if index < len(bits) else 0
                index += 1
                if _mask_condition(mask, row, c):
                    bit ^= 1
                matrix.set(row, c, bit, reserve=False)
        upward = not upward
        col -= 2


_N3_PATTERN = [1, 0, 1, 1, 1, 0, 1]


def _finder_like_penalty(line: list[int], size: int) -> int:
    score = 0
    i = 0
    while i <= size - 7:
        if line[i:i + 7] != _N3_PATTERN:
            i += 1
            continue
        if not any(line[max(i - 4, 0):i]) or not any(line[i + 7:i + 11]):
            score += 40
            i += 7
        else:
            # Pas assez de modules clairs autour : on repart du dernier module
            # sombre du motif, seul point de depart possible pour un chevauchement.
            i += 4
    return score


def _penalty(matrix: _Matrix) -> int:
    size = matrix.size
    modules = matrix.modules
    score = 0

    # Regle 1 : suites de 5 modules ou plus de meme couleur
    for line in list(modules) + [list(col) for col in zip(*modules)]:
        run, previous = 1, line[0]
        for value in line[1:]:
            if value == previous:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run, previous = 1, value
        if run >= 5:
            score += 3 + (run - 5)

    # Regle 2 : blocs 2x2 de meme couleur
    for r in range(size - 1):
        for c in range(size - 1):
            block = modules[r][c] + modules[r][c + 1] + modules[r + 1][c] + modules[r + 1][c + 1]
            if block in (0, 4):
                score += 3

    # Regle 3 : motif 1:1:3:1:1 borde par 4 modules clairs (la zone de silence
    # hors symbole compte comme claire, cf. ISO/IEC 18004:2015 tableau 11)
    for line in list(modules) + [list(col) for col in zip(*modules)]:
        score += _finder_like_penalty(line, size)

    # Regle 4 : desequilibre clair/sombre
    dark = sum(sum(row) for row in modules)
    ratio = dark * 100 // (size * size)
    score += 10 * (abs(ratio - 50) // 5)
    return score


def _build_matrix(data: list[int], version: int, ec_level: str, mask: int) -> _Matrix:
    size = version * 4 + 17
    matrix = _Matrix(size)
    _place_finder(matrix, 0, 0)
    _place_finder(matrix, 0, size - 7)
    _place_finder(matrix, size - 7, 0)
    _place_alignment(matrix, version)
    _place_timing(matrix)
    _reserve_format(matrix, version)
    _place_data(matrix, data, mask)
    _apply_format(matrix, ec_level, mask)
    _apply_version(matrix, version)
    return matrix


def encode(text: str, ec_level: str = "M") -> list[list[int]]:
    """Retourne la matrice du QR code (1 = module sombre)."""
    if ec_level not in ("L", "M"):
        raise QRError("Seuls les niveaux L et M sont supportes")
    data = text.encode("utf-8")
    version = _pick_version(len(data), ec_level)
    codewords = _build_codewords(data, version, ec_level)
    interleaved = _interleave(codewords, version, ec_level)

    best: tuple[int, _Matrix] | None = None
    for mask in range(8):
        matrix = _build_matrix(interleaved, version, ec_level, mask)
        score = _penalty(matrix)
        if best is None or score < best[0]:
            best = (score, matrix)
    assert best is not None
    return best[1].modules


def to_svg(text: str, ec_level: str = "M", quiet_zone: int = 4, dark: str = "#00287E") -> str:
    """Rend le QR code en SVG autonome (mise a l'echelle par le navigateur)."""
    modules = encode(text, ec_level)
    size = len(modules) + quiet_zone * 2

    path: list[str] = []
    for r, row in enumerate(modules):
        c = 0
        while c < len(row):
            if row[c]:
                start = c
                while c < len(row) and row[c]:
                    c += 1
                path.append(f"M{start + quiet_zone} {r + quiet_zone}h{c - start}v1h-{c - start}z")
            else:
                c += 1

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'shape-rendering="crispEdges" role="img" aria-label="QR code">'
        f'<rect width="{size}" height="{size}" fill="#ffffff"/>'
        f'<path fill="{dark}" d="{"".join(path)}"/>'
        f"</svg>"
    )
