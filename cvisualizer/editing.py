"""Small lexical helpers for editor conveniences; independent from C execution."""


def context(text):
    """Return lexical state and unmatched opening braces before the cursor."""
    state, braces, i = 'code', [], 0
    while i < len(text):
        char = text[i]
        pair = text[i:i+2]
        if state == 'line_comment':
            if char == '\n':
                state = 'code'
        elif state == 'block_comment':
            if pair == '*/':
                state = 'code'
                i += 1
        elif state in ('"', "'"):
            if char == '\\':
                i += 1
            elif char == state:
                state = 'code'
        elif pair == '//':
            state = 'line_comment'
            i += 1
        elif pair == '/*':
            state = 'block_comment'
            i += 1
        elif char in ('"', "'"):
            state = char
        elif char == '{':
            braces.append(i)
        elif char == '}' and braces:
            braces.pop()
        i += 1
    return state, braces


def escaped(text):
    return (len(text) - len(text.rstrip('\\'))) % 2 == 1
