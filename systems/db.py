from peewee import SqliteDatabase, Model

db = SqliteDatabase('dev.db')

class BaseModel(Model):
    class Meta:
        database = db