import os
import xml.etree.ElementTree as ET

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

API_KEY = os.environ.get("KRDICT_API_KEY", "")
TRANS_LANG = os.environ.get("KRDICT_TRANS_LANG", "9")
BASE_URL = "https://krdict.korean.go.kr/api"

mcp = FastMCP(
    "KRDict Korean Dictionary",
    instructions=(
        "Korean Standard Dictionary (KRDict) tools for Korean learners. "
        "Use these tools to search Korean vocabulary and retrieve Indonesian meanings."
    ),
)


def text(element, tag):
    if element is None:
        return ""

    child = element.find(tag)

    if child is None or child.text is None:
        return ""

    return child.text.strip()


async def krdict_request(endpoint, params):
    if not API_KEY:
        raise RuntimeError(
            "KRDICT_API_KEY belum dikonfigurasi di server."
        )

    request_params = {
        "key": API_KEY,
        **params,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{BASE_URL}/{endpoint}",
            params=request_params,
        )

    response.raise_for_status()

    root = ET.fromstring(response.content)

    if root.tag == "error":
        code = text(root, "error_code")
        message = text(root, "message")

        raise RuntimeError(
            f"KRDict API error {code}: {message}"
        )

    return root


def format_search_item(item):
    word = text(item, "word")
    pronunciation = text(item, "pronunciation")
    pos = text(item, "pos")
    grade = text(item, "word_grade")
    target_code = text(item, "target_code")

    lines = []

    header = f"## {word}"

    if pronunciation:
        header += f" [{pronunciation}]"

    lines.append(header)

    if pos:
        lines.append(f"- 품사: {pos}")

    if grade:
        lines.append(f"- tingkat: {grade}")

    if target_code:
        lines.append(f"- target_code: {target_code}")

    senses = item.findall("sense")

    for index, sense in enumerate(senses, 1):
        translation = sense.find("translation")

        trans_word = text(translation, "trans_word")
        trans_definition = text(translation, "trans_dfn")
        korean_definition = text(sense, "definition")

        line = f"{index}. "

        if trans_word:
            line += trans_word

        if trans_definition:
            line += f" — {trans_definition}"

        if korean_definition:
            line += f"\n   한국어 뜻: {korean_definition}"

        lines.append(line)

    return "\n".join(lines)


@mcp.tool()
async def search_word(
    query: str,
    limit: int = 10,
) -> str:
    """
    Cari kosakata Korea di KRDict.

    Contoh:
    search_word("먹다")
    search_word("학교")
    """

    limit = max(10, min(limit, 100))

    root = await krdict_request(
        "search",
        {
            "q": query,
            "part": "word",
            "num": limit,
            "sort": "dict",
            "translated": "y",
            "trans_lang": TRANS_LANG,
        },
    )

    items = root.findall("item")

    if not items:
        return f"Tidak ditemukan hasil untuk: {query}"

    results = [
        format_search_item(item)
        for item in items
    ]

    return "\n\n".join(results)


@mcp.tool()
async def word_detail(target_code: str) -> str:
    """
    Ambil detail sebuah kosakata berdasarkan target_code KRDict.

    Gunakan target_code yang diperoleh dari search_word.
    """

    root = await krdict_request(
        "view",
        {
            "method": "target_code",
            "q": target_code,
            "translated": "y",
            "trans_lang": TRANS_LANG,
        },
    )

    item = root.find("item")

    if item is None:
        return f"Entri tidak ditemukan: {target_code}"

    info = item.find("word_info")

    if info is None:
        return "Format detail KRDict tidak dikenali."

    word = text(info, "word")
    pronunciation = text(info, "pronunciation")
    pos = text(info, "pos")
    grade = text(info, "word_grade")

    output = [
        f"# {word}",
    ]

    if pronunciation:
        output.append(f"Pelafalan: {pronunciation}")

    if pos:
        output.append(f"Part of speech: {pos}")

    if grade:
        output.append(f"Tingkat: {grade}")

    senses = info.findall("sense_info")

    for index, sense in enumerate(senses, 1):
        translation = sense.find("translation")

        trans_word = text(translation, "trans_word")
        trans_definition = text(translation, "trans_dfn")
        korean_definition = text(sense, "definition")

        output.append(f"\n## Arti {index}")

        if trans_word:
            output.append(f"- Indonesia: {trans_word}")

        if trans_definition:
            output.append(f"- Penjelasan: {trans_definition}")

        if korean_definition:
            output.append(
                f"- 한국어 뜻: {korean_definition}"
            )

        examples = sense.findall("example_info")

        for example in examples:
            example_text = text(example, "example")

            if example_text:
                output.append(
                    f"- Contoh: {example_text}"
                )

    return "\n".join(output)


@mcp.tool()
async def search_definition(query: str) -> str:
    """
    Cari kosakata berdasarkan definisi/arti.
    """

    root = await krdict_request(
        "search",
        {
            "q": query,
            "part": "dfn",
            "num": 20,
            "sort": "dict",
            "translated": "y",
            "trans_lang": TRANS_LANG,
        },
    )

    items = root.findall("item")

    if not items:
        return f"Tidak ditemukan kata dengan definisi: {query}"

    return "\n\n".join(
        format_search_item(item)
        for item in items
    )


@mcp.tool()
async def search_example(query: str) -> str:
    """
    Cari kosakata berdasarkan contoh penggunaan.
    """

    root = await krdict_request(
        "search",
        {
            "q": query,
            "part": "exam",
            "num": 20,
            "sort": "dict",
            "translated": "y",
            "trans_lang": TRANS_LANG,
        },
    )

    items = root.findall("item")

    if not items:
        return f"Tidak ditemukan contoh untuk: {query}"

    return "\n\n".join(
        format_search_item(item)
        for item in items
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse(
        {
            "ok": True,
            "service": "krdict-mcp",
        }
    )


app = mcp.streamable_http_app(
    stateless_http=True
)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        stateless_http=True,
    )
