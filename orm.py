from peewee import *

db_auth = SqliteDatabase('auth.db')

class Auth(Model):
    usuario = CharField()
    clave_publica = CharField()

    class Meta:
        database = db_auth 