from tdparser import Lexer, Parser, Token, ParserError
from tdparser.topdown import EndToken

lexer = Lexer()


class Key(Token):
    regexp = r'[A-Za-z_][A-Za-z0-9_]*'

    def nud(self, context):
        return self


class Number(Token):
    regexp = r'-?\d+'
    type = 'int'

    def __init__(self, text):
        Token.__init__(self, text)
        self.value = int(text)

    def nud(self, context):
        return self


class String(Token):
    regexp = r'"(?:[^\\"]|\\\\|\\")*"'
    type = 'str'

    def __init__(self, text):
        Token.__init__(self, text)
        self.value = text[1:-1].replace('\\"', '"').replace('\\\\', '\\')

    def nud(self, context):
        return self


class Operator(Token):
    regexp = r'[=<>]'
    lbp = 10

    def led(self, left, context):
        right = context.expression(self.lbp)
        inverted = False
        if not isinstance(left, Key) and isinstance(right, Key):
            left, right = right, left
            inverted = True
        elif not isinstance(left, Key):
            raise ParserError("Condition does not involve a key")
        elif isinstance(right, Key):
            raise ParserError("Condition involves two keys")
        if self.text == '=':
            cond = 'equal'
        elif self.text == '<':
            cond = 'gt' if inverted else 'lt'
        elif self.text == '>': # pragma: no branch
            cond = 'lt' if inverted else 'gt'
        return left.text, {'type': right.type, cond: right.value}


lexer.register_tokens(Key, Number, String, Operator)


def _update_conditions(conditions, expr):
    key, cond = expr
    prec = conditions.get(key)
    if prec is not None:
        if prec['type'] != cond['type']:
            raise ParserError("Differing types for conditions on key %s: "
                              "%s, %s" % (key, prec['type'], cond['type']))
        for k in cond.keys():
            if k != 'type' and k in prec:
                raise ParserError("Multiple conditions %s on key %s" % (
                                  k, key))
        prec.update(cond)
    else:
        conditions[key] = cond


def parse_expression(expression):
    tokens = lexer.lex(expression)
    parser = Parser(tokens)
    conditions = {}
    while not isinstance(parser.current_token, EndToken):
        expr = parser.expression()
        if isinstance(expr, Token):
            raise ParserError("Found unexpected token %s in query" % expr)
        _update_conditions(conditions, expr)
    return conditions


def parse_expressions(expression_list):
    conditions = {}
    for expression in expression_list:
        expr = lexer.parse(expression)
        if isinstance(expr, Token):
            raise ParserError("Found unexpected token %s in query" % expr)
        _update_conditions(conditions, expr)
    return conditions
