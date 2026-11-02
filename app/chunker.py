from typing import List


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    """
    Splits text into chunks of approximately `chunk_size` characters with `overlap`.
    Attempts to break cleanly on paragraph breaks, then newlines, then sentence boundaries or spaces.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks = []
    start = 0
    text_len = len(cleaned)

    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            chunk = cleaned[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # Look for natural split point within overlap window
        # Ideal split boundaries in order of preference:
        # 1. Double newline (paragraph)
        # 2. Single newline
        # 3. Sentence end ('. ', '? ', '! ')
        # 4. Space
        window_start = max(start, end - overlap)
        split_point = -1

        slice_for_search = cleaned[window_start:end]

        double_nl = slice_for_search.rfind("\n\n")
        if double_nl != -1:
            split_point = window_start + double_nl + 2
        else:
            single_nl = slice_for_search.rfind("\n")
            if single_nl != -1:
                split_point = window_start + single_nl + 1
            else:
                for punct in [". ", "? ", "! "]:
                    p_idx = slice_for_search.rfind(punct)
                    if p_idx != -1:
                        split_point = max(split_point, window_start + p_idx + 2)

                if split_point == -1:
                    space_idx = slice_for_search.rfind(" ")
                    if space_idx != -1:
                        split_point = window_start + space_idx + 1

        if split_point == -1 or split_point <= start:
            split_point = end

        chunk = cleaned[start:split_point].strip()
        if chunk:
            chunks.append(chunk)

        # Advance start with overlap consideration
        start = max(start + 1, split_point - overlap if split_point < text_len else text_len)

    return chunks
