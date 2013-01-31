from devassistant.cli import argparse_generator
from devassistant.cli import path_runner
from devassistant import settings

class CliRunner(object):
    @classmethod
    def run_assistant(cls, assistant):
        ch = assistant.get_subassistant_chain()
        parsed_args = argparse_generator.ArgparseGenerator.generate_argument_parser(ch).parse_args()
        path = assistant.get_subassistant_path(getattr(parsed_args, settings.SUBASSISTANTS_STRING))
        pr = path_runner.PathRunner(path, parsed_args)
        pr.run()