from peewee import SqliteDatabase, Model
from .orm import orm_get_all_models

db = SqliteDatabase('dev.db')

class BaseModel(Model):
    class Meta:
        database = db

def initialize_db():
    db.connect()
    db.create_tables(orm_get_all_models())
    db.close()