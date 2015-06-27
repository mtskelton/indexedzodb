import uuid

import ZODB
import persistent
import BTrees
import transaction


class DoesNotExist(Exception):
    pass


class DuplicateIndex(Exception):
    pass


class ZODBModel(persistent.Persistent):
    _id = None
    _v_reindex = False

    class Meta:
        table = "zodbmodel"
        index_fields = ()

    def __init__(self, *args, **kwargs):
        for key in kwargs:
            value = kwargs[key]
            if hasattr(self, key):
                setattr(self, key, value)

    @classmethod
    def _get_index_fields(cls):
        try:
            return cls.Meta.index_fields
        except AttributeError:
            return ()

    @classmethod
    def _get_connection(cls):
        try:
            return cls.Meta.connection
        except AttributeError:
            zodb = ZODB.DB(None)
            cls.Meta.connection = zodb.open()
            return cls.Meta.connection

    @classmethod
    def _get_model_root(cls):
        root = cls._get_connection().root
        if not hasattr(root, cls.Meta.table):
            model_root = BTrees.OOBTree.BTree()
            setattr(root, cls.Meta.table, model_root)
            model_root['indexes'] = BTrees.OOBTree.BTree()
            model_root['objects'] = BTrees.OOBTree.BTree()
        return getattr(root, cls.Meta.table)

    @classmethod
    def _get_root(cls):
        model_root = cls._get_model_root()
        return model_root['objects']

    @classmethod
    def _get_index_root(cls, field):
        model_root = cls._get_model_root()
        index_root = model_root['indexes']
        if field not in index_root:
            index_root[field] = BTrees.OOBTree.BTree()
        return index_root[field]

    @classmethod
    def index(cls):
        for field in cls._get_index_fields():
            index_root = cls._get_index_root(field)
            index_root.clear()

        for o in cls.select():
            for field in cls._get_index_fields():
                index_root = cls._get_index_root(field)
                index_root[getattr(o, field)] = o._id

    def _remove_from_index(self, field, value):
        """
        Remove this from the given index as the field value has changed
        """
        if not self._id:
            return

        index_root = self._get_index_root(field)
        if value in index_root:
            del index_root[value]

    def _add_to_index(self, field, value):
        """
        Update the index .. field by field
        """
        if not self._id or not value:
            return

        index_root = self._get_index_root(field)
        index_root[value] = self._id

    @classmethod
    def select(cls, *args, **kwargs):
        if len(kwargs) == 1 and kwargs.keys()[0] in cls._get_index_fields():
            # We can use an index table
            index_root = cls._get_index_root(kwargs.keys()[0])
            value = kwargs[kwargs.keys()[0]]
            if value in index_root:
                return [cls._get_root()[index_root[value]]]
            return []

        cmps = []
        for key in kwargs:
            try:
                value = kwargs[key].replace("'", "\'")
            except AttributeError:
                value = kwargs[key]
            key = key.replace("'", "\'")

            if isinstance(value, int):
                cmps.append("x.%s == %d" % (key, value))
            else:
                cmps.append("x.%s == '%s'" % (key, value))

        if len(cmps) == 0:
            return list(cls._get_root().values())

        cmp_func = lambda x: eval(' and '.join(cmps))
        return filter(lambda x: cmp_func(x), cls._get_root().values())

    @classmethod
    def count(cls, *args, **kwargs):
        return len(cls.select(*args, **kwargs))

    @classmethod
    def get(cls, *args, **kwargs):
        try:
            return cls.select(*args, **kwargs)[0]
        except IndexError:
            raise DoesNotExist()

    def _get_safe_key(self, root):
        key = uuid.uuid1().hex
        while key in root:
            key = uuid.uuid1().hex
        return key

    @classmethod
    def commit(cls):
        transaction.commit()

    def save(self, commit=True):
        # Check for duplicate values in the index fields
        for field in self._get_index_fields():
            index_root = self._get_index_root(field)
            value = getattr(self, field)
            if value in index_root and index_root[value] != self._id:
                raise DuplicateIndex("Indexed field %s contains duplicate value %s" % (field, value))

        root = self._get_root()
        if not self._id:
            self._id = self._get_safe_key(root)
        root[self._id] = self

        if self._v_reindex:
            for field in self._get_index_fields():
                self._add_to_index(field, getattr(self, field))
            self._v_reindex = False

        if commit:
            transaction.commit()

    def delete(self, commit=True):
        root = self._get_root()
        if self._id:
            del root[self._id]
            self._id = None

        if commit:
            transaction.commit()

    def getPk(self):
        return self._id

    def __str__(self, *args, **kwargs):
        return str(self.getPk())

    def __unicode__(self, *args, **kwargs):
        return unicode(self.getPk())

    def __setattr__(self, name, value):
        if name[0] != '_' and name in self._get_index_fields() and getattr(self, name) != value:
            self._v_reindex = True
            self._remove_from_index(name, getattr(self, name))

        persistent.Persistent.__setattr__(self, name, value)
