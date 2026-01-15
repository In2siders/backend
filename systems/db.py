from os import getenv
from peewee import SqliteDatabase, PostgresqlDatabase

db_uri = getenv('PGDB_CONNECTION')
db = PostgresqlDatabase(db_uri)