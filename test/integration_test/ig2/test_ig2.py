import importlib.util
import json
from pathlib import Path

from linkml_runtime.loaders import yaml_loader

from text_parser_generator.generator import typed_from_yaml, TextParserGenerator
from text_parser_generator.model import Schema, TypeSpec, Attribute


def test_ig2():
    # conf = yaml_loader.load((Path(__file__).parent / 'schema.yaml').read_text(), Schema)
    conf: Schema = typed_from_yaml((Path(__file__).parent / 'schema.yaml').read_text(), Schema)
    generator = TextParserGenerator(conf)
    generator.run()
    schema_module = generator.load_module()

    # stream = io.StringIO('Name  2 1 24\tABC   \tDEF    \nName2   1 2 3\tGHI  \tJKL\n')
    file_path = Path(r'D:\SteamLibrary\steamapps\common\Industry Giant 2\config\Config.gen')
    # with open(file_path, 'r', encoding='cp1252') as stream:
    with open(file_path, 'rb') as stream:
    # with open(file_path, 'rb', 0) as stream:
        test_schema = schema_module.IG2(stream, encoding='cp1252')
    assert len(test_schema.tables) == 67
    schema_dict = test_schema.as_dict()
    with open('parsed.json', 'w') as stream:
        json.dump(schema_dict, stream, indent=4)
    _ = 42

    all_column_types = {
        table_type
        for table in schema_dict['tables']
        for table_type in table['column_types']
    }
    print(all_column_types)

    # TODO currently the cell values are not type cast or stripped or anything - Guess it would make sense
    #  to remove cast and use type and then built the conversion functionalities in the type
    #  like int, number, etc. There is also a way in kaitai to have a switch-on <expr> with cases for the type
    #  that could work with the types of IG2 to handle cells depending on the column


if __name__ == '__main__':
    test_ig2()
