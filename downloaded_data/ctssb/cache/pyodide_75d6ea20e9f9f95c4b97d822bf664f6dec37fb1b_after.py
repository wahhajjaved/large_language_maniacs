def test_pandas(selenium):
    selenium.load_package("pandas")
    assert len(selenium.run("import pandas\ndir(pandas)")) == 179


def test_extra_import(selenium):
    selenium.run("from pandas import Series, DataFrame, Panel")
