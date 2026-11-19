
from app.database.database import initialize_database
from app.services.question_bank_importer import import_all_roles


def main():

    print("Initializing question bank database...")

    initialize_database()

    print("Importing role question bank...")

    import_all_roles()


if __name__ == "__main__":
    main()
