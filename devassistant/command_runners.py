import copy
import functools
import getpass
import logging
import os

import yaml

from devassistant import exceptions
from devassistant import command
from devassistant.command_helpers import ClHelper, DialogHelper
from devassistant.logger import logger
from devassistant.package_managers import DependencyInstaller
from devassistant import settings
from devassistant import utils
from devassistant import version
from devassistant import yaml_snippet_loader

command_runners = []

def register_command_runner(command_runner):
    command_runners.append(command_runner)
    return command_runner

@register_command_runner
class CallCommandRunner(object):
    @classmethod
    def matches(cls, c):
        return c.comm_type == 'call'

    @classmethod
    def run(cls, c):
        sect_type = c.kwargs['__section__']
        assistant = c.kwargs['__assistant__']
        section = cls.get_section_from_call(c.comm, sect_type, assistant)
        if not section:
            msg = 'Couldn\'t find {t} section "{n}".'.format(t=c.kwargs['__section__'],
                                                             n=c.comm)
            logger.warning(msg)
            return [] if sect_type == 'dependencies' else None

        if cls.is_snippet_call(c.comm):
            # we're calling a snippet => add files and files_dir to kwargs
            snippet = yaml_snippet_loader.YamlSnippetLoader.get_snippet_by_name(c.comm.split('.')[0])

            c.kwargs['__files__'].append(snippet.get_files_section())
            c.kwargs['__files_dir__'].append(snippet.get_files_dir())

        if sect_type == 'dependencies':
            result = assistant._dependencies_section(section, copy.deepcopy(c.kwargs))
        else:
            result = assistant._run_one_section(section, copy.deepcopy(c.kwargs))

        if cls.is_snippet_call(c.comm):
            c.kwargs['__files__'].pop()
            c.kwargs['__files_dir__'].pop()

        return result

    @classmethod
    def is_snippet_call(cls, cmd_call):
        return not (cmd_call == 'self' or cmd_call.startswith('self.'))

    @classmethod
    def get_section_from_call(cls, cmd_call, section_type, assistant):
        """Returns a section form call.

        Examples:
            if section_type == dependencies, then
              cmd_call == self.dependencies_bar returns content of dependencies_bar from this assistant
            if section_type == run, then
              cmd_call == self.run_foo returns run_foo of this assistant
              cmd_call == eclipse.run_python returns run_python section of eclipse snippet

        Args:
            cmd_call - a string with the call, e.g. "eclipse.run_python"
            section_type - either "dependencies" or "run"
            assistant - current assistant for the possibility of trying to use "self"

        Returns:
            section to run - dict, None if not found
        """

        section = None
        call_parts = cmd_call.split('.')
        section_name = call_parts[1] if len(call_parts) > 1 else section_type

        if call_parts[0] == 'self':
            section = getattr(assistant, '_' + section_name, None)
        else: # snippet
            try:
                snippet = yaml_snippet_loader.YamlSnippetLoader.get_snippet_by_name(call_parts[0])
                if section_type == 'run':
                    section = snippet.get_run_section(section_name) if snippet else None
                else:
                    section = snippet.get_dependencies_section(section_name) if snippet else None
            except exceptions.SnippetNotFoundException:
                section = None

        return section

@register_command_runner
class ClCommandRunner(object):
    @classmethod
    def matches(cls, c):
        return c.comm_type.startswith('cl')

    @classmethod
    def run(cls, c):
        comm = c.format_str()
        log_level = logging.DEBUG
        log_error = True
        if 'i' in c.comm_type:
            log_level = logging.INFO
        if 'n' in c.comm_type:
            log_error = False
        scls = []
        if '__scls__' in c.kwargs:
            scls = functools.reduce(lambda x, y: x + y, c.kwargs['__scls__'], scls)
        try:
            result = ClHelper.run_command(comm, log_level, scls=scls)
        except exceptions.ClException as e:
            if log_error:
                try:
                    logger.error(unicode(e))
                except:
                    logger.error(e)
            raise e

        return result.strip() if hasattr(result, 'strip') else result

@register_command_runner
class DependenciesCommandRunner(object):
    @classmethod
    def matches(cls, c):
        return c.comm_type.startswith('dependencies')

    @classmethod
    def run(cls, c):
        if c.comm_type == 'dependencies':
            struct = c.format_list()

        di = DependencyInstaller()
        di.install(struct)

@register_command_runner
class DotDevassistantCommandRunner(object):
    @classmethod
    def matches(cls, c):
        return c.comm_type.startswith('dda_')

    @classmethod
    def run(cls, c):
        comm = c.format_str()
        if c.comm_type == 'dda_c':
            return cls._dot_devassistant_create(comm, **c.kwargs)
        elif c.comm_type == 'dda_r':
            return cls._dot_devassistant_read(comm, **c.kwargs)
        elif c.comm_type == 'dda_dependencies':
            return cls._dot_devassistant_dependencies(comm, **c.kwargs)
        elif c.comm_type == 'dda_run':
            return cls._dot_devassistant_run(comm, **c.kwargs)
        else:
            logger.warning('Unknown .devassistant command {0}, skipping.'.format(c.comm_type))

    @classmethod
    def _dot_devassistant_create(cls, directory, **kwargs):
        cls._dot_devassistant_path = os.path.join(directory, '.devassistant')
        f = open(cls._dot_devassistant_path, 'w')
        # write path to this subassistant
        path = []
        i = 0
        while settings.SUBASSISTANT_N_STRING.format(i) in kwargs:
            path.append(kwargs[settings.SUBASSISTANT_N_STRING.format(i)])
            # delete the dict member so that we don't write it out with other kwargs again
            del kwargs[settings.SUBASSISTANT_N_STRING.format(i)]
            i += 1

        if path and path[0] in settings.ASSISTANT_ROLES:
            path = path[1:]

        # we will only write original cli/gui args, other kwargs are "private" for this run
        original_kwargs = {}
        arg_names = map(lambda arg: arg.name, kwargs['__assistant__'].args)
        for arg in arg_names:
            if arg in kwargs: # only write those that were actually used on invocation
                original_kwargs[arg] = kwargs[arg]
        to_write = {'devassistant_version': version.VERSION,
                    'subassistant_path': path,
                    'original_kwargs': original_kwargs}
        yaml.dump(to_write, stream=f, default_flow_style=False)
        f.close()

    @classmethod
    def _dot_devassistant_read(cls, comm, **kwargs):
        """Don't use this directly from assistants (yet), raises uncaught exception
        if anything goes wrong.
        Reads and returns data from .devassistant file. On top of it, it adds:
        - "name" - contains the name of current directory.
        - "dda__<var>" - (yes, that is double underscore) - for each <var> that
          this project was created with.
        """
        dot_devassistant = os.path.join(os.path.abspath(os.path.expanduser(comm)), '.devassistant')
        try:
            with open(dot_devassistant, 'r') as stream:
                result = yaml.load(stream)
        except IOError as e:
            msg = 'Couldn\'t find properly formatted .devassistant file: {0}'.format(e)
            logger.error(msg)
            raise exceptions.RunException(msg)

        for k, v in result.get('original_kwargs', {}).items():
            result['dda__' + k] = v
        result['name'] = os.path.basename(os.path.abspath(os.path.expanduser(comm)))
        return result

    @classmethod
    def _dot_devassistant_dependencies(cls, comm, **kwargs):
        struct = []
        dda_content = cls._dot_devassistant_read(comm, **kwargs)
        original_assistant_path = dda_content.get('subassistant_path', [])
        if original_assistant_path:
            # if we have an original path, try to get original assistant
            original_path_as_dict = {}
            for i, subas in enumerate(original_assistant_path):
                original_path_as_dict[settings.SUBASSISTANT_N_STRING.format(i)] = subas
            from devassistant.bin import CreatorAssistant
            from devassistant import yaml_assistant
            try:
                path = CreatorAssistant().get_selected_subassistant_path(**original_path_as_dict)
            except exceptions.AssistantNotFoundException as e:
                path = []
                logger.warning(str(e))
            for a in path:
                #TODO: maybe figure out more DRY code (similar is in path_runner, too)
                if 'dependencies' in vars(a.__class__) or isinstance(a, yaml_assistant.YamlAssistant):
                    struct.extend(a.dependencies(**dda_content.get('original_kwargs', {})))
            struct.extend(kwargs['__assistant__']._dependencies_section(dda_content.get('dependencies', []), **kwargs))
        command.Command('dependencies', struct, **kwargs).run()

    @classmethod
    def _dot_devassistant_run(cls, comm, **kwargs):
        dda_content = cls._dot_devassistant_read(comm, **kwargs)
        return kwargs['__assistant__']._run_one_section(dda_content.get('run', []), kwargs)

class GitHubAuth(object):
    _user = None
    _token = None
    try:
        _gh_module = utils.import_module('github')
    except:
        _gh_module = None

    @classmethod
    def _github_login(cls, **kwargs):
        return kwargs['github'] or getpass.getuser()

    @classmethod
    def _github_token(cls, **kwargs):
        if not cls._token:
            try:
                cls._token = ClHelper.run_command("git config github.token.{login}".format(
                    login=cls._github_login(**kwargs)))
            except exceptions.ClException:
                pass # token is not available yet

        return cls._token

    @classmethod
    def _get_github_user(cls, login, token, **kwargs):
        if not cls._user:
            try:
                # try logging with token
                gh = cls._gh_module.Github(login_or_token=token)
                cls._user = gh.get_user()
                # try if the authentication was successful
                cls._user.login
            except cls._gh_module.GithubException:
                # if the token was set, it was wrong, so make sure it's reset
                cls._token = None
                # login with username/password
                password = DialogHelper.ask_for_password(
                        prompt='Github Password for {username}:'.format(username=login))
                gh = cls._gh_module.Github(login_or_token=login, password=password)
                cls._user = gh.get_user()
                try:
                    cls._user.login
                    cls._github_create_auth(**kwargs) # create auth for future use
                except cls._gh_module.GithubException as e:
                    msg = 'Wrong username or password\nGitHub exception: {0}'.format(e)
                    logger.error(msg)
                    # reset cls._user to None, so that we don't use it if calling this multiple times
                    cls._user = None
                    raise exceptions.RunException(msg)
        return cls._user

    @classmethod
    def _github_create_auth(cls, **kwargs):
        """ Store token into ~/.gitconfig.

        If token is not defined then store it into ~/.gitconfig file
        """
        if not cls._token:
            try:
                auth = cls._user.create_authorization(scopes=['repo', 'user'], note="DeveloperAssistant")
                ClHelper.run_command("git config --global github.token.{login} {token}".format(
                    login=cls._user.login,
                    token=auth.token))
                ClHelper.run_command("git config --global github.user.{login} {login}".format(
                    login=cls._user.login))
            except cls._gh_module.GithubException as e:
                logger.warning('Creating authorization failed: {0}'.format(e))

    @classmethod
    def _github_create_ssh_key(cls, **kwargs):
        try:
            login = cls._user.login
            pkey_path = '{home}/.ssh/{keyname}'.format(home=os.path.expanduser('~'),
                                                       keyname=settings.GITHUB_SSH_KEYNAME.format(login=login))
            # create ssh keys here
            if not os.path.isfile('{pkey_path}.pub'.format(pkey_path=pkey_path)):
                ClHelper.run_command('ssh-keygen -t rsa -f {pkey_path}\
                                     -N \"\" -C \"DeveloperAssistant\"'.\
                                     format(pkey_path=pkey_path))
                ClHelper.run_command('ssh-add {pkey_path}'.format(pkey_path=pkey_path))
            public_key = ClHelper.run_command('cat {pkey_path}.pub'.format(pkey_path=pkey_path))
            # find out if this key is already registered with this user
            for key in cls._user.get_keys():
                # don't use "==" because we have comments etc added in public_key
                if key._key in public_key:
                    break
            else:
                cls._user.create_key("devassistant", public_key)
            # next, create ~/.ssh/config entry for the key, if system username != GH login
            cls._github_create_ssh_config_entry(**kwargs)
        except exceptions.ClException:
            pass # TODO: determine and log the error

    @classmethod
    def _github_create_ssh_config_entry(cls, **kwargs):
        if getpass.getuser() != cls._user.login:
            ssh_config = os.path.expanduser('~/.ssh/config')
            user_github_string = 'github.com-{0}'.format(cls._user.login)
            needs_to_add_config_entry = True

            if os.path.isfile(ssh_config):
                fh = open(ssh_config)
                config_content = fh.read()
                if user_github_string in config_content:
                    needs_to_add_config_entry = False
                fh.close()
            if needs_to_add_config_entry:
                fh = os.fdopen(os.open(ssh_config, os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o600), 'a')
                fh.write(settings.GITHUB_SSH_CONFIG.format(
                            login=cls._user.login,
                            keyname=settings.GITHUB_SSH_KEYNAME.format(login=cls._user.login)))
                fh.close()

    @classmethod
    def github_authenticated(cls, func):
        """Does user authentication, creates SSH keys if needed and injects "_user" attribute
        into class/object bound to the decorated function.
        Don't call any other methods of this class manually, this should be everything you need.
        """
        def inner(func_cls, *args, **kwargs):
            if not cls._gh_module:
                logger.warning('PyGithub not installed, skipping github authentication procedures.')
            elif not func_cls._user:
                # authenticate user, possibly also creating authentication for future use
                func_cls._user = cls._get_github_user(cls._github_login(**kwargs),
                                                  cls._github_token(**kwargs),
                                                  **kwargs)
                # create ssh key for pushing
                cls._github_create_ssh_key(**kwargs)
            func(func_cls, *args, **kwargs)

        return inner

@register_command_runner
class GitHubCommandRunner(object):
    _user = None
    try:
        _gh_module = utils.import_module('github')
    except:
        _gh_module = None

    @classmethod
    def matches(cls, c):
        return c.comm_type == 'github'

    @classmethod
    def run(cls, c):
        comm = c.format_str()
        if not cls._gh_module:
            logger.warning('PyGithub not installed, cannot execute github command.')
            return
        if comm == 'create_repo':
            cls._github_create_repo(**c.kwargs)
        elif comm == 'push':
            cls._github_push(**c.kwargs)
        elif comm == 'create_and_push':
            cls._github_create_and_push(**c.kwargs)
        else:
            logger.warning('Unknow github command {0}, skipping.'.format(comm))

    @classmethod
    def _github_reponame(cls, **kwargs):
        """Extracts reponame from name, which is possibly a path."""
        return os.path.basename(kwargs['name'])

    @classmethod
    def _github_push_repo(cls, **kwargs):
        ClHelper.run_command("git push -u origin master", logging.INFO)

    @classmethod
    def _github_remote_show_origin(cls, **kwargs):
        ClHelper.run_command("git remote show origin")

    @classmethod
    @GitHubAuth.github_authenticated
    def _github_add_remote_origin(cls, **kwargs):
        reponame = cls._github_reponame(**kwargs)
        # if system username != GH login, we need to use git@github.com-{login}:...
        # else just git@github.com:...
        dash_login = ''
        if getpass.getuser() != cls._user.login:
            dash_login = '-' + cls._user.login
        ClHelper.run_command("git remote add origin git@github.com{dash_login}:{login}/{reponame}.git".\
                             format(dash_login=dash_login, login=cls._user.login, reponame=reponame), logging.INFO)

    @classmethod
    @GitHubAuth.github_authenticated
    def _github_create_repo(cls, **kwargs):
        """Create repo on GitHub.

        If repository already exists then RunException will be raised.

        Raises:
            devassistant.exceptions.RunException on error
        """
        reponame = cls._github_reponame(**kwargs)

        if reponame in map(lambda x: x.name, cls._user.get_repos()):
            msg = 'Repository already exists on GitHub'
            logger.error(msg)
            raise exceptions.RunException(msg)
        else:
            try:
                new_repo = cls._user.create_repo(reponame)
            except cls._gh_module.GithubException:
                msg = 'Failed to create GitHub repo. This sometime happens when you delete '
                msg += 'a repo and then you want to create the same one immediately. Wait '
                msg += 'for few minutes and then try again.'
                logger.error(msg)
                raise exceptions.RunException(msg)
            logger.info('Your new repository: {0}'.format(new_repo.html_url))

    @classmethod
    @GitHubAuth.github_authenticated
    def _github_push(cls, **kwargs):
        """Add a remote and push to GitHub.

        Raises:
            devassistant.exceptions.RunException on error
        """
        cls._github_add_remote_origin(**kwargs)
        cls._github_remote_show_origin(**kwargs)
        cls._github_push_repo(**kwargs)

    @classmethod
    @GitHubAuth.github_authenticated
    def _github_create_and_push(cls, **kwargs):
        # we assume we're in the project directory
        logger.info('Registering your project on GitHub as {0}/{1}...'.format(cls._user.login,
                                                                              cls._github_reponame(**kwargs)))
        cls._github_create_repo(**kwargs)
        logger.info('Pushing your project to the new GitHub repository...')
        cls._github_push(**kwargs)
        logger.info('GitHub repository was created and source code pushed.')

@register_command_runner
class LogCommandRunner(object):
    @classmethod
    def matches(cls, c):
        return c.comm_type.startswith('log_')

    @classmethod
    def run(cls, c):
        comm = c.format_str()
        if c.comm_type in map(lambda x: 'log_{0}'.format(x), settings.LOG_LEVELS_MAP):
            logger.log(logging._levelNames[settings.LOG_LEVELS_MAP[c.comm_type[-1]]], comm)
            if c.comm_type[-1] in 'ce':
                raise exceptions.RunException(comm)
        else:
            logger.warning('Unknown logging command {0} with message {1}'.format(c.comm_type, comm))
