from unittest.case import TestCase
import unittest

import ZODB

from indexedzodb.models import ZODBModel, DuplicateIndex


zodb = ZODB.DB(None)
connection = zodb.open()


class Company(ZODBModel):
    name = None
    established = 0

    class Meta:
        table = "company"
        connection = connection
        index_fields = ('name', )


class LocalDataTest(TestCase):
    def setUp(self):
        TestCase.setUp(self)

    def tearDown(self):
        TestCase.tearDown(self)

    def test_basic_models(self):
        self.assertTrue(Company.count() == 0)

        Company(name="Brickmakers Inc", established=1989).save()
        Company(name="Timmy's Tea Mugs", established=1980).save()
        Company(name="Seaside Cafe", established=2005).save()

        self.assertTrue(Company.count() == 3)
        self.assertTrue(len(Company.select(established=2005)) == 1)

        try:
            Company(name="Seaside Cafe", established=2005).save()
            raise AssertionError("Duplicate index check failed")
        except DuplicateIndex:
            pass

        # Check remove from index
        c = Company.get(name='Seaside Cafe')
        c.delete()

        Company(name="Seaside Cafe", established=2005).save()


if __name__ == '__main__':
    unittest.main()
