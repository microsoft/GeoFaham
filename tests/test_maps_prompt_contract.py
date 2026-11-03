"""Keep executable Maps prompt examples compatible with actual tool arguments."""
import ast
import inspect
import re
import unittest

from pydantic import TypeAdapter
from agents.maps_agent import tools
from agents.maps_agent._prompts import SYS_PROMPT


class MapsPromptContractTests(unittest.TestCase):
    def test_examples_use_supported_parameters_and_enum_values(self):
        examples = re.findall(r'```python\n(.*?)```', SYS_PROMPT, re.S)
        self.assertTrue(examples, 'Maps prompt must retain worked tool examples')
        for example in examples:
            for call in ast.walk(ast.parse(example)):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                    continue
                with self.subTest(tool=call.func.id, example=example):
                    function = getattr(tools, call.func.id)
                    signature = inspect.signature(function)
                    args = [ast.literal_eval(arg) for arg in call.args]
                    kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
                    bound = signature.bind(*args, **kwargs)
                    for name, value in bound.arguments.items():
                        annotation = signature.parameters[name].annotation
                        if annotation is not inspect.Parameter.empty:
                            TypeAdapter(annotation).validate_python(value)


if __name__ == '__main__':
    unittest.main()
