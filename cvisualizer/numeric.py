"""Platform-independent numeric storage used by the teaching interpreter."""


class Long(int):
    pass


class Char(int):
    pass


def type_name(names):
    return 'long' if 'long' in names else names[0]
