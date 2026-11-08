"""One test method per entry of a table, so each entry passes, fails and is timed on its own, and
the runner can spread a long table across processes."""
import re


def one_test_each(cls, prefix, table, check):
    """Add test_<prefix>_<entry name> to cls for each entry of table, calling check(self, name, entry)."""
    for name, entry in table.items():
        method = "test_%s_%s" % (prefix, re.sub(r"[^0-9a-z]+", "_", str(name).lower()).strip("_"))
        if hasattr(cls, method):
            raise ValueError(f"two entries of the table make {method}")

        def test(self, name=name, entry=entry):
            check(self, name, entry)

        test.__name__, test.__qualname__, test.__doc__ = method, f"{cls.__name__}.{method}", None
        setattr(cls, method, test)
