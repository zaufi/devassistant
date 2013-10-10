Tutorial: Creating Your Own Assistant
=====================================

So you want to create your own assistant? There is nothing easier... They say
that in all tutorials, right?

This tutorial will guide you through the process of creating simple assistants
of :ref:`different roles <assistant_roles_devel>` - Creator, Modifier,
Preparer.

This tutorial doesn't cover everything. Consult :ref:`yaml_assistant_reference`
when you're missing something you really need to achieve. If you think
that DevAssistant misses some functionality that would be useful, open
a bug at https://www.github.com/bkabrda/devassistant/issues or send us
a pull request.

Common Rules and Gotchas
------------------------

Some things are common for all assistant types:

- Each assistant is one Yaml file, that must contain exactly one mapping
  of assistant name to all the assistant contents. E.g::

   assistant:
     fullname: My Assistant
     description: This will be part of help for this assistant
     ...

- You have to place them in a proper place, see :ref:`load_paths` and
  :ref:`assistants_loading_mechanism`.
- When creating templates (pre-created files used by assistants), they should
  be placed in the same load dir, e.g. if your assistant is placed at
  ``~/.devassistant/assistants``, it will look for templates under
  ``~/.devassistant/templates``.
- As mentioned in :ref:`load_paths`, there are three main load paths in
  standard DevAssistant installation, "system", "local" and "user".
  The "system" dir is used for assistants delivered by your
  distribution/packaging system and you shouldn't touch or add files in
  this path. The "local" path can be used by system admins to add system-wide
  assistants while not touching "system" path. Lastly, "user" path can be
  used by users to create and use their own assistants. It is up to you where
  you place your assistant, but "user" path is usually best for playing around
  and development of new assistants. It is also the path that we will use
  throughout these tutorials.

Creating a Simple Creator
-------------------------

The title says it all. In this section, we will create a "Creator" assistant,
that means an assistant that will take care of kickstarting a new project.
We will write an assistant that creates a project containing a simple Python
script that uses ``argh`` Python module. Let's suppose that we're writing
this assistant for an RPM based system like Fedora, CentOS or RHEL.

This assistant is a "creator", so we have to put it somewhere into
``~/.devassistant/assistants/crt/``. Since the standard DevAssistant
distribution has a ``python`` assistant, it seems logical to make this new
assistant a subassistant of ``python``. That means that the assistant file
will be ``~/.devassistant/assistants/creator/python/argh.yaml``. It doesn't
matter that the ``python`` assistant actually lives in a different load path,
DevAssistant will hook the ``argh`` subassistant properly anyway.

Setting it Up
~~~~~~~~~~~~~

So, let's start writing our assistant by providing some initial metadata::

   argh:
     fullname: Argh Script Template
     description: Create a template of simple script that uses argh library

If you now save the file and run ``da crt python argh -h``, you'll see that
your assistant was already recognized by DevAssistant, although it doesn't
provide any functionality yet.

Dependencies
~~~~~~~~~~~~

Now, we'll want to add a dependency on ``python-argh`` (which is how the
package is called e.g. on Fedora). You can do this just by adding::

   dependencies:
   - rpm: [python-argh]

Now, if you save the file and actually try to run your assistant with
``da crt python argh``, it will install ``python-argh``! (Well, assuming
it's not already installed, in which case it will do nothing.) This is
really super-cool, but the assistant still doesn't do any project setup,
so let's get on with it.

Files
~~~~~

Since we want the script to always look the same, we will create a file that
our assistant will copy into proper place. This file should be put into
into ``crt/python/argh`` subdirectory the template directory
(``~/.devassistant/files/crt/python/argh``). The file will be called
``arghscript.py`` and will have this content::

   #!/usr/bin/python2

   from argh import *

   def main():
       return 'Hello world'

   dispatch_command(main)

We will need to refer to this file from our assistant, so let's open
``argh.yaml`` again and add a ``files`` section::

   files:
     arghs: &arghs
       source: arghscript.py

DevAssistant will automatically search for this file in the correct directory,
that is ``~/.devassistant/files/crt/python/argh``.
If there are e.g. some files common to multiple ``python`` subassistants, it
is reasonable to place them into ``~/.devassistant/files/crt/python`` and
refer to them with relative path like ``../file.foo``

Run
~~~

Finally, we will be adding a ``run`` section, which is the section that does
all the hard work. A ``run`` section is a list of **commands**. Every command
is in fact a Yaml mapping with exactly one key and value. The key determines
**command type**, while value is the **command input**. For example, ``cl`` is
a **command type** that says that given **input** should be run on commandline,
``log_i`` is a **command type** that lets us print the **input** (message in
this case) for user, etc.

Let's start writing our ``run`` section::

   run:
   - log_i: Hello, I'm Argh assistant and I will create an argh project for you.

But wait! We don't know what the project should be called and where it
should be placed... Before we finish the ``run`` section, we'll need to add
some arguments to our assistant.

Oh Wait, Arguments!
~~~~~~~~~~~~~~~~~~~

Creating any type of project typically requires some user input, at least name
of the project to be created. To ask user for this sort of information, we can
use DevAssistant arguments like this::

   args:
     name:
       flags: [-n, --name]
       required: True
       help: 'Name of project to create'

This means that this assistant will have one argument called ``name``. On
commandline, it will expect ``-n foo`` or ``--name foo`` and since the
argument is required, it will refuse to run without it.

You can now try running ``da crt python argh -h`` and you'll see that the
argument is printed out in commandline help.

Since there are some common arguments, the standard installation of
DevAssistant ships with so called "snippets", that contain (among other
things) definitions of frequentyl used arguments. You can use name argument
for Creator assistants like this::

   args:
     name:
       snippet: common_args

Run Again
~~~~~~~~~

Now that we can obtain the desired name, let's continue. Now that we have the
project name (let's assume that it's an arbitrary path to a directory where
the argh script should be placed), we can continue. First, we will make sure
that the directory doesn't already exist. If so, we need to exit, because we
don't want to overwrite or break something::

   run:
   - log_i: Hello, I'm Argh assistant and I will create an argh project for you.
   - if $(test -e "$name"):
     - log_e: '"$name" already exists, can't proceed.'

There are few things to note here:

- There is a simple ``if`` condition with a shell command. If the shell command
  returns a non-zero value, the condition will evaluate to false, else it will
  evaluate to true. So in this case, if something exists at path ``"$name"``,
  the condition will evaluate to true.
- In any command, we can use value of the ``name`` argument by prefixing
  argument name with ``$`` (so  ``$name`` or ``${name}``).
- The ``log_e`` command type is used to print a message and then abort the
  assistant execution immediately.

Let's continue by creating the directory. Add this line to ``run`` section::

   - cl: mkdir -p "$name"

You may be wondering what will happen, if DevAssistant doesn't have write
permissions or more generally if the ``mkdir`` command just fails. In this
case, DevAssistant will exit, printing the output of failed command for user.

Next, we want to copy our script into the directory. We want to name it the
same as name of the directory itself. But what if directory is a path, not
simple name? We have to find out the project name and remember it somehow::

   - $proj_name: $(basename "$name")

What just happened? We assigned output of command ``basename "$name"`` to
a new variable ``proj_name`` that we can use from now on. So let's copy
the script and make it executable::

   - cl: cp *arghs ${name}/${proj_name}.py
   - cl: chmod +x ${name}/${proj_name}.py

One thing to note here is, that by using ``*arghs``, we reference a file
from the ``files`` section.

Now, we'll use a super-special command::

   - dda_c: "$name"

What is ``dda_c``? The first part, ``dda`` stands for "dot devassistant file",
the second part, ``_c``, says, that we want to create this file (there are
more things that can be done with ``.devassistant`` file, see TODO).
The "command" part of this call just says where the file should be stored,
which is ``$name`` directory in our case.

The ``.devassistant`` file serves for storing meta information about the
project. Amongst other things, it stores information about which assistant was
invoked. This information can later serve to prepare the environment (e.g.
install ``python-argh``) on another machine or so. Assuming that we commit the
project to a git repository, one just needs to run
``da prep custom -u <repo_url>``, and DevAssistant will checkout the project
from git and use information stored in ``.devassistant`` to reinstall
dependencies. (There is more to this, you can for example add a custom
``run`` section to ``.devassistant`` file or add custom dependencies,
but this is not covered by this tutorial (not even by reference, so I need to
place TODO here to document it).)

*Note: There can be more dependencies sections and run sections in one
assistant. To find out more about the rules of when they're used and how
run sections can call each other, consult*
:ref:`dependencies reference <dependencies_ref>` *and*
:ref:`run reference <run_ref>`.

Something About Snippets
~~~~~~~~~~~~~~~~~~~~~~~~

Wait, did we say git? Wouldn't it be nice if we could setup a git repository
inside the project directory and do an initial commit? These things are always
the same, which is exactly the type of task that DevAssistant should do for
you.

Previously, we've seen usage of argument from snippet. But what if you could
use a part of ``run`` section from there? Well, you can. And you're lucky,
since there is a snippet called ``git_init_add_commit``, which does exactly
what we need. We'll use it like this::

   - cl: cd "$name"
   - call: git_init_add_commit

This calls section ``run`` from snippet ``git_init_add_commit`` in this place.
Note, that all variables are "global" and the snippet will have access to them
and will be able to change their values. However, variables defined in called
snippet section will not propagate into current section.

Finished!
~~~~~~~~~

It seems that everything is set. It's always nice to print a message that
everything went well, so we'll do that and we're done::

   - log_i: Project "$proj_name" has been created in "$name".

The Whole Assistant
~~~~~~~~~~~~~~~~~~~

... looks like this::

   argh:
     fullname: Argh Script Template
     description: Create a template of simple script that uses argh library

     dependencies:
     - rpm: [python-argh]

     files:
       arghs: &arghs
         source: arghscript.py

     args:
       name:
         snippet: common_args

     run:
     - log_i: Hello, I'm Argh assistant and I will create an argh project for you.
     - if $(test -e "$name"):
       - log_e: '"$name" already exists, cannot proceed.'
     - cl: mkdir -p "$name"
     - $proj_name: $(basename "$name")
     - cl: cp *arghs ${name}/${proj_name}.py
     - cl: chmod +x *arghs ${name}/${proj_name}.py
     - dda_c: "$name"
     - cl: cd "$name"
     - call: git_init_add_commit
     - log_i: Project "$proj_name" has been created in "$name".

And can be run like this: ``da crt python argh -n foo/bar``.


Creating a Modifier
-------------------

*This section assumes that you've read the previous tutorial and are therefore
familiar with DevAssistant basics.*
Modifiers are meant to modify existing projects, that means projects with
``.devassistant`` file (there is also an option to write assistant that
modifies an arbitrary project without ``.devassistant``, read on).

Modifier Specialties
~~~~~~~~~~~~~~~~~~~~

On invocation of a modifier, DevAssistant tries to read ``.devassistant``
file from path specified by ``path`` argument, if the assistant has such
argument. Otherwise, it tries to read it from current directory. It the
file is not found, DevAssistant fails immediately. If you don't want
DevAssistant to look for and read ``.devassistant``, you need to specify
``devassistant_projects_only: False``, see reference for
:ref:`modifier_assistants_ref`.

Another specialty of modifiers is, that DevAssistant tries to search for more
``dependencies`` sections to use. If the project was previously created by
``crt python django``, the engine will install dependencies from sections
``dependencies_python_django``, ``dependencies_python`` and ``dependencies``.

Also, the engine will try to run ``run_python_django`` section first, then it
will try ``run_python`` and then ``run`` - note, that this will only run the
first found section and then exit, unlike with dependencies, where all found
sections are used.
