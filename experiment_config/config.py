import os
import sys
import warnings
import traceback
import colorama as cr
from copy import deepcopy

from ruamel.yaml import YAML, CommentedMap

cr.init()
yaml = YAML()


class ConfigError(Exception):
    """
    The default Experiment Config Exception
    """
    pass


class ConfigKeyError(ConfigError):
    """
    Exception for when a required parameter is missing.
    """
    pass


class ConfigTypeError(ConfigError):
    """
    Exception for when a parameter value type does
    not match that specified in the `@parameter` decorator.
    """
    pass


class ConfigAssertionError(ConfigError):
    """
    Exception when a parameter value is not valid.
    Raised if an assert statement in the config
    parameter definitions fails.
    """
    pass


class ConfigWarning(UserWarning):
    """
    The default Experiment Config warning.
    """
    pass


class ConfigKeyWarning(ConfigWarning):
    """
    Warning version of ConfigKeyError.
    """
    pass


class ConfigTypeWarning(ConfigWarning):
    """
    Warning version of ConfigTypeError.
    """
    pass


class ConfigAssertionWarning(ConfigWarning):
    """
    Warning version of ConfigAssertionError.
    """
    pass


class ConfigVersionWarning(ConfigWarning):
    """
    Warning for when the current git version does not
    match the version read from a yaml file by
    `BaseConfig.from_yaml_file()`.
    """
    pass


class ParameterDeprecationWarning(ConfigWarning):
    """
    Warning for when a parameter is deprecated.
    """
    pass


def format_error_str():
    _, _, tb = sys.exc_info()
    summ = traceback.extract_tb(tb)[-1]
    err_str = f"{summ.name}\n {summ.filename} {summ.lineno}: {summ.line}"
    return err_str


def reformat_comment(comment):
    """
    Reformats python docstrings to work as yaml comments.
    """
    if comment is None:
        return None
    lines = comment.strip().split('\n')
    lines = [line.strip() for line in lines]
    return '\n'.join(lines)


class Parameter(object):
    """
    A single config parameter.

    :param str name: The parameter name.
    :param Any value: The value of this parameter.
    :param Any default: The default value of this parameter.
    :param type types: A type or tuple of types.
    :param function validation: A function to run for validating the
                                value of this parameter.
    :param str comment: An optional comment to attach to this parameter.
    :param bool deprecated: Whether this parameter has been deprecated.
    """

    def __init__(self, name, value=None, default=None, types=None,
                 validation=None, comment=None, deprecated=False):
        self.name = name
        self._value = value
        self.default = default
        if self._value is None and self.default is not None:
            self._value = self.default
        self.types = types
        self.validation = validation
        self.comment = comment
        self.deprecated = deprecated
        if self.deprecated is True:
            warnings.warn(f"Parameter '{self.name}' is deprecated.",
                          ParameterDeprecationWarning)
        if self.value is not None:
            self.validate()

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self.validate()

    def infer_default_value(self):
        """
        Try to infer a default value of this parameter from
        its types.
        """
        if self.default is not None:
            return self.default
        if self.types is None:
            return None
        if isinstance(self.types, (tuple, list)):
            t = self.types[0]
        else:
            t = self.types
        return t()

    def validate(self):
        if self.types is not None:
            if not isinstance(self.value, self.types):
                self.value = self._try_cast(self.value, self.types)
        if self.validation is not None:
            self.validation(self.value)

    def _try_cast(self, value, types):
        """
        Try to cast value as one of types.

        :param Any value: The value to try to cast
        :param (tuple, type) types: A type or tuple of types.
        :returns: The cast value or None if casting failed.
        """
        if isinstance(value, types):
            return value
        if not isinstance(types, (tuple, list)):
            types = [types]
        casted = None
        for typ in types:
            try:
                casted = typ(value)
            except ValueError:
                pass
        if casted is None:
            raise ConfigTypeError(f"{self.name}: {self.value} ({type(self.value)}) not of type {self.types}./")  # noqa
        return casted

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.value == other.value

    def __str__(self):
        return self.pretty_print()

    def __repr__(self):
        return f"Parameter({self.name}, value={self.value})"

    def _pretty_print_comment(self, indent=0):
        if self.comment is None:
            return ''
        indent_str = ' ' * indent
        lines = self.comment.split('\n')
        lines = [indent_str + f" # {line}" for line in lines]
        return '\n'.join(lines) + '\n'

    def pretty_print(self, indent=0):
        indent_str = ' ' * indent
        comment_str = self._pretty_print_comment(indent)
        format_str = comment_str + indent_str + f" • {self.name}: {self.value}"
        if self.deprecated is True:
            format_str = cr.Fore.RED + format_str + " (deprecated)"
            format_str += cr.Style.RESET_ALL
        return format_str + '\n'

    def asdict(self, indent=0):
        d = CommentedMap({self.name: self.value})
        d.yaml_set_comment_before_after_key(self.name, before=self.comment,
                                            indent=indent)
        if self.deprecated is True:
            d.yaml_add_eol_comment("(deprecated)", self.name)
        return d


class ParameterGroup(object):
    """
    A group of config parameters.

    :param str name: The name of this group.
    :param str comment: An optional comment.
    """

    def __init__(self, name, comment=None):
        self.name = name
        self.comment = comment
        self.members = []

    def add(self, param_or_group, index=None):
        """
        Add a subgroup or Parameter to this group.

        :param (ParameterGroup, Parameter) param_or_group:
            the group or parameter to add.
        :param int index: Where to add this element in the members list.
        """
        if param_or_group.name in self.members:
            raise KeyError(f"{param_or_group.name} already in group {self.name}.")  # noqa
        if index is not None:
            self.members.insert(index, param_or_group.name)
        else:
            self.members.append(param_or_group.name)
        setattr(self, param_or_group.name, param_or_group)

    def __iter__(self):
        for member in self.members:
            yield getattr(self, member)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        for this_member_name in self.members:
            this_member = getattr(self, this_member_name)
            that_member = getattr(other, this_member_name, None)
            if this_member != that_member:
                return False
        return True

    def __str__(self):
        members_str = ','.join(self.members)
        return f"ParameterGroup(name={self.name}, members={members_str})"

    def __repr__(self):
        return f"ParameterGroup({self.name})"

    def pretty_print(self, indent=0):
        formatted = ""
        indent_str = ' ' * indent
        group_str = cr.Style.BRIGHT + indent_str + \
            f"{self.name}\n" + cr.Style.RESET_ALL
        formatted += group_str
        for member in self:
            next_indent = indent
            if isinstance(member, ParameterGroup):
                next_indent += 1
            formatted += member.pretty_print(indent=next_indent)
        return formatted

    def asdict(self, indent=0):
        self_dict = CommentedMap({self.name: CommentedMap()})
        self_dict.yaml_set_comment_before_after_key(
            self.name, before=self.comment, indent=indent)
        for member in self:
            # update() doesn't preserve comments
            # and I can't set the ca attribute directly
            # so I have to go through _yaml_comment
            # It's very ugly.
            member_dict = member.asdict(indent=indent+2)
            self_dict[self.name].update(member_dict)
            if self_dict[self.name].ca is not None:
                self_dict[self.name]._yaml_comment.items.update(
                    member_dict.ca.items)
        return self_dict


class Config(object):

    """
    The base experiment config class, which is used to create your own config.
    The keyword arguments used to initialize
    your subclass are those methods which you decorate with @parameter.

    .. code-block:: python

        from experiment_config import Config

        myconfig = Config("MyConfig")

        @myconfig.parameter(group="Foo/Bar", types=int, default=50)
        def parameter1(value):
            # Add any initialization/validation code here
            assert value > 0
            assert value < 90

        @myconfig.parameter(group="Foo/Bar", types=int, default=60)
        def parameter2(value):
            # Add any initialization/validation code here
            assert value > 10
            assert value < 100

        @myconfig.on_load
        def validate_parameters(myconfig):
            assert myconfig.parameter2 == myconfig.parameter1 + 10

        myconfig.Foo.Bar.parameter1  # prints 50 (the default)
        myconfig.Foo.Bar.parameter2  # prints 60 (the default)
    """

    def __init__(self, name):
        self.name = name
        self.GROUPS = []
        self.git = ParameterGroup("Git")
        for (key, value) in self._git_info().items():
            self.git.add(Parameter(key, value))

    def load_yaml(self, filepath, errors="raise"):
        """
        Loads a config from the specified yaml file.

        :param str filepath: Path to the .yaml file.
        :param str errors: "raise" or "warn"
        """
        with open(filepath, 'r') as inF:
            config_dict = yaml.load(inF)
        self.load_dict(config_dict, errors=errors)

    def load_dict(self, config_dict, errors="raise"):
        """
        Loads a config from a dictionary

        :param dict config_dict: dict object with the same group/parameter
                                 structure as this Config instance.
        :param str errors: "raise" or "warn"
        """
        for group_name in self.GROUPS:
            group = getattr(self, group_name)
            self._init_param_or_group(
                group, check_default_values=True, **config_dict[group_name],
                errors=errors)
        try:
            self._post_load_hook()
        except AssertionError:
            err_str = format_error_str()
            if errors == "ignore":
                pass
            elif errors == "warn":
                warnings.warn(err_str, ConfigAssertionWarning)
            else:
                raise ConfigAssertionError(err_str)

    def _init_param_or_group(self, param_or_group, check_default_values=True,
                             errors="raise", **kwargs):
        if isinstance(param_or_group, ParameterGroup):
            group = param_or_group
            these_kwargs = kwargs
            for member in group:
                if isinstance(member, ParameterGroup):
                    these_kwargs = kwargs[member.name]
                self._init_param_or_group(
                    member, check_default_values=check_default_values,
                    errors=errors, **these_kwargs)
        else:
            param = param_or_group
            try:
                param.value = kwargs[param.name]
            except KeyError:
                if param.default is None:
                    if check_default_values is True:
                        err_str = f"Missing required parameter '{param.name}'."
                        if errors == "ignore":
                            pass
                        elif errors == "warn":
                            warnings.warn(err_str, ConfigKeyWarning)
                        else:
                            raise ConfigKeyError(err_str)
                    else:
                        param._value = param.infer_default_value()
                else:
                    param.value = param.default
            except AssertionError:
                err_str = format_error_str()
                if errors == "ignore":
                    pass
                elif errors == "warn":
                    warnings.warn(err_str, ConfigAssertionWarning)
                else:
                    raise ConfigAssertionError(err_str)

    def _post_load_hook(self):
        """
        Can be overridden using the on_load decorator. See usage.
        """
        pass

    def parameter(self, group="Default", default=None, types=None,
                  deprecated=False):
        """
        A decorator for marking a config parameter.

        :param str group: (Optional) The group to add this parameter to.
                          Groups and subgroups can be specified using dots,
                          e.g., 'Parent.Child'.
                          If not specified, adds the Default group.
        :param Any default: (Optional) If specified, sets a default
                            value for this parameter.
        :param type types: (Optional) Can be a single type or a tuple of
                          types. If specified, restricts the values to
                          these types.
        :param bool deprecated: If True, set this parameter as deprecated.
        """
        def wrapper(func):
            group_names = group.split('.')
            current_group = self
            for name in group_names:
                try:
                    current_group = getattr(current_group, name)
                except AttributeError:
                    new_group = ParameterGroup(name)
                    index = None
                    if name == "Default":
                        index = 0
                    current_group.add(new_group, index=index)
                    current_group = new_group
            fn_name = func.__name__
            comment = reformat_comment(func.__doc__)
            param = Parameter(fn_name, types=types, default=default,
                              validation=func, comment=comment,
                              deprecated=deprecated)
            current_group.add(param)
            return property(func)
        return wrapper

    def on_load(self, func):
        """
        A decorator for setting a function to run after loading a config
        with load_yaml or load_dict. See usage for Config.
        """
        self._post_load_hook = func

    def add(self, param_or_group, index=None):
        """
        Add a Parameter or ParameterGroup to this config at
        the specified index. If index is None, appends to the end.

        :param (Parameter, ParameterGroup) param_or_group:
            The parameter or group to add.
        :param int index: Where to add this element to the members list.
        """
        # If we're trying to add a Parameter directly
        # then it will be put in the Default group.
        if isinstance(param_or_group, Parameter):
            if "Default" not in self.GROUPS:
                self.add(ParameterGroup("Default"), index=0)
            group = getattr(self, "Default")
            group.add(param_or_group)
        elif isinstance(param_or_group, ParameterGroup):
            if index is not None:
                self.GROUPS.insert(index, param_or_group.name)
            else:
                self.GROUPS.append(param_or_group.name)
            setattr(self, param_or_group.name, param_or_group)

    def update(self, param_name, new_value, group="Default"):
        """
        Update the value of param_name under the specified group.

        :param str param_name: The name of the Parameter whose value to update.
        :param Any new_value: The new value of this Parameter.
        :param str group: This Parameter's group. Can use the dot '.' syntax.
        """
        group_names = group.split('.')
        current_group = self
        for name in group_names:
            current_group = getattr(current_group, name)
        param = getattr(current_group, param_name)
        param.value = new_value
        self._post_load_hook()

    def __str__(self):
        formatted = cr.Style.BRIGHT + self.name + '\n'
        formatted += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        formatted += cr.Style.RESET_ALL
        for group_name in self.GROUPS:
            group = getattr(self, group_name)
            formatted += group.pretty_print()
        if self.git is not None:
            formatted += self.git.pretty_print()
        formatted += cr.Style.BRIGHT + "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        formatted += cr.Style.RESET_ALL
        return formatted.strip()

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        for group_name in self.GROUPS:
            this_group = getattr(self, group_name)
            that_group = getattr(other, group_name, None)
            if this_group != that_group:
                return False
        return True

    def copy(self):
        """
        Copy this Config instance.
        """
        new_instance = deepcopy(self)
        new_instance.name = self.name + "-copy"
        return new_instance

    def yaml(self, outpath=None):
        """
        Format this config as yaml.
        If outpath is None, returns a str.
        Otherwise, save the yaml to outpath.

        :param str outpath: (Optional) Where to save the yaml file.
        """
        if outpath is None:
            yaml.dump(self.asdict(), sys.stdout)
        else:
            with open(outpath, 'w') as outF:
                yaml.dump(self.asdict(), outF)

    def asdict(self):
        """
        Format this config as a dict.
        """
        config_dict = CommentedMap()
        for group_name in self.GROUPS:
            group = getattr(self, group_name)
            config_dict.update(group.asdict())
        config_dict["Git"] = self._git_info()
        return config_dict

    def _git_info(self):
        # log commit hash
        with os.popen("git rev-parse --abbrev-ref HEAD") as p:
            branch = p.read().strip()
        with os.popen("git log --pretty=format:'%h' -n 1") as p:
            commit = p.read().strip()
        with os.popen("git remote -v | tail -n 1") as p:
            url = p.read().strip().split()[1]
        if branch == '':
            branch = None
        if commit == '':
            commit = None
        if url == '':
            url = None
        if None in (branch, commit, url):
            warnings.warn("Error getting current git information. Are you in a git repo?",  # noqa
                          ConfigWarning)
            return None
        return {"branch": branch, "commit": commit, "url": url}
