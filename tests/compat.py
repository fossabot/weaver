try:
    import six
    if six.PY2:
        import contextlib2 as contextlib  # noqa
    else:
        import contextlib
except ImportError:
    raise
