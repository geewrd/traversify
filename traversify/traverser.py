import json
import inspect
import re
import copy


IDENTIFIER_REGEX = re.compile(r'^[a-zA-Z_]\w*$')


def split_escaped(path):
    return [k.replace('KQypbNUMED', '.') for
            k in path.replace('..', 'KQypbNUMED').split('.')]


def is_identifier(key):
    return IDENTIFIER_REGEX.match(str(key)) is not None


def traversable(value):
    return type(value) in [list, dict]


def wrap_value(value, deepcopy=False, filter=None):
    return Traverser(value, deepcopy=deepcopy, filter=filter) if traversable(value) else value


def unwrap_value(value):
    return value() if isinstance(value, Traverser) else value


def recursively_unwrap_value(recursive_value):
    recursive_value = unwrap_value(recursive_value)
    if type(recursive_value) == list:
        return [recursively_unwrap_value(v) for v in recursive_value]
    elif type(recursive_value) == dict:
        return dict([(k, recursively_unwrap_value(v)) for k, v in recursive_value.items()])
    return recursive_value


def ensure_list(value):
    return value if type(value) == list else [value]


class Traverser(object):
    def __init__(self, value, deepcopy=True, filter=None):
        if hasattr(value, 'json') and inspect.ismethod(value.json):
            value = value.json()
        if isinstance(value, str):
            value = json.loads(value)
        if not traversable(value):
            raise ValueError("Only list or dict types allowed: '{}'".format(value))
        if deepcopy:
            value = recursively_unwrap_value(value)
        self.__traverser__internals__ = {
            'value': value,
            'filter': filter,
        }

    def __call__(self, path=None, value=None):
        if path is not None and value is None:
            return self._find(path)
        elif None not in (path, value):
            return self._set(path, value)
        elif value and path is None:
            raise ValueError('path argument cannot be None when value argument is not None')
        else:
            return self.__traverser__internals__['value']

    def to_json(self):
        return json.dumps(self())

    def __dir__(self):
        dir_list = dir(Traverser)
        value = self()
        if type(value) == dict:
            dir_list.extend([k for k in value.keys() if is_identifier(k)])
        return dir_list

    def __getattr__(self, attr, default=None):
        if '__traverser__internals__' in attr:
            return super(Traverser, self).__getattribute__('__traverser__internals__')
        return self.get(attr, default)

    def __setattr__(self, attr, value):
        if '__traverser__internals__' in attr:
            super(Traverser, self).__setattr__('__traverser__internals__', value)
        else:
            self[attr] = value

    def __repr__(self):
        return 'Traverser({})'.format(json.dumps(self(), indent=2, default=str))

    def __str__(self):
        return 'Traverser({})'.format(json.dumps(self(), indent=2, default=str))

    def get(self, attr, default=None):
        value = self().get(attr, default)
        return wrap_value(value)

    def _find(self, path):

        def get(node, _keys):
            _key = _keys.pop(0)
            if isinstance(node(), list):
                try:
                    _key = int(_key)
                except ValueError:
                    pass
            try:
                next_node = node.get(_key)
            except (AttributeError, TypeError, IndexError):
                return None
            if not _keys:
                return next_node
            if not isinstance(next_node, Traverser):
                return None
            return get(next_node, _keys)

        keys = split_escaped(path)
        return get(self, keys)

    def _set(self, path, value, force=True, deepcopy=False):
        if deepcopy:
            return self.__deepcopy__()._set(path, value, force, False)

        def set_(node, _keys, parent=None, parent_key=None):
            _key = _keys.pop(0)
            try:
                _key = int(_key)
                if not isinstance(node(), list):
                    parent[parent_key] = [{}]
                    node = parent.get(parent_key)
                    _key = 0
                else:
                    if abs(_key) >= len(node):
                        parent.get(parent_key).append({})
                        _key = len(node) - 1 if _key >= 0 else 0
                    node = parent.get(parent_key)
            except ValueError:
                if not node or not isinstance(node(), dict):
                    parent[parent_key] = {}
                    node = parent(parent_key)
            if not _keys:
                node[_key] = value
                return self
            return set_(node.get(_key), _keys, node, _key)

        keys = split_escaped(path)
        return set_(self, keys)

    def ensure_list(self, item):
        value = self.get(item)
        if value is None:
            return None
        if isinstance(value, Traverser):
            return value
        return [value]

    def __getitem__(self, index):
        if isinstance(index, str):
            return self.get(index)
        else:
            value = self()
            if type(value) != list:
                value = [value]
            if isinstance(index, type(slice(0))):
                start = 0 if index.start is None else index.start
                stop = len(value) if index.stop is None else index.stop
                value = value[start:stop]
            else:
                value = value[index]
            return wrap_value(value)

    def __setitem__(self, index, value):
        self()[index] = recursively_unwrap_value(value)

    def __eq__(self, other):
        if self.__traverser__internals__['filter'] is None:
            return self() == unwrap_value(other)
        else:
            return self.__traverser__internals__['filter'].are_equal(self, other)

    def prune(self, filter=None):
        if filter is None:
            filter = self.__traverser__internals__['filter']
        if filter is not None:
            filter.prune(self)
        return self

    def __contains__(self, item):
        for value in self:
            if value == item:
                return True
        return False

    def __len__(self):
        value = self()
        return len(value) if type(value) == list else 1

    def __bool__(self):
        return bool(len(self))

    def __delitem__(self, item):
        del self()[item]

    def append(self, item):
        value = self()
        item = unwrap_value(item)
        if type(value) == list:
            value.append(item)
        else:
            self.__traverser__internals__['value'] = [value, item]
        return self

    def extend(self, item):
        value = self()
        items = ensure_list(unwrap_value(item))
        if type(value) == list:
            value.extend(items)
        else:
            self.__traverser__internals__['value'] = [value] + items
        return self

    def __delattr__(self, item):
        del self()[item]

    def __iter__(self):
        value = self()
        if type(value) == list:
            result = []
            for value in value:
                result.append(wrap_value(value))
            return iter(result)
        else:
            return iter([self])

    def __add__(self, item):
        value = ensure_list(self())
        item = ensure_list(unwrap_value(item))
        return wrap_value(value + item)

    def __copy__(self):
        return Traverser(copy.copy(self()))

    def __deepcopy__(self, memo=None):
        return Traverser(copy.deepcopy(self()))


class Filter(object):
    def __init__(self, blacklist=None, whitelist=None):
        self.blacklist = [] if blacklist is None else ensure_list(blacklist)
        self.whitelist = [] if whitelist is None else ensure_list(whitelist)

    def are_equal(self, left, right):
        left_value = unwrap_value(left)
        right_value = unwrap_value(right)

        if type(left_value) == type(right_value) == list:
            if len(left_value) != len(right_value):
                return False
            for index, item in enumerate(left_value):
                if not self.are_equal(item, right_value[index]):
                    return False
            return True

        elif type(left_value) == type(right_value) == dict:
            left_keys = sorted(left_value.keys())
            right_keys = sorted(right_value.keys())
            if self.blacklist:
                left_keys = [k for k in left_keys if k not in self.blacklist]
                right_keys = [k for k in right_keys if k not in self.blacklist]
            if self.whitelist:
                left_keys = [k for k in left_keys if k in self.whitelist]
                right_keys = [k for k in right_keys if k in self.whitelist]
            if left_keys != right_keys:
                return False
            for key in left_keys:
                if not self.are_equal(left_value[key], right_value[key]):
                    return False
            return True

        else:
            return left_value == right_value

    def prune(self, value):
        value = unwrap_value(value)

        if type(value) == list:
            for item in value:
                self.prune(item)

        elif type(value) == dict:
            keys = list(value.keys())
            if self.blacklist:
                keys = [k for k in keys if k not in self.blacklist]
            if self.whitelist:
                keys = [k for k in keys if k in self.whitelist]
            for key in list(value.keys()):
                if key in keys:
                    self.prune(value[key])
                else:
                    del value[key]
