"""Platform-independent numeric storage used by the teaching interpreter."""


class Long(int):
    pass


class LongLong(Long):
    pass


class Char(int):
    pass


def type_name(names):
    return 'long long' if names.count('long') == 2 else 'long' if 'long' in names else 'bool' if names[0] == '_Bool' else names[0]
