# from runner import *
#
# devices = ['ADAMSOLA001']
#
#
# print("\nFiltered Records with Issuance History Changes:")
# filtered_records = fetch_records_with_issuance_history_changes(devices, days=7)
# print("Type: ", type(filtered_records))
# if not filtered_records:
#     print("No records found with changes in issuance history in the last 7 days.")
# else:
#     for record in filtered_records:
#         print(
#             f"Filtered Record - Name: {record.name}, Address: {record.address}, Country: {record.country}, Issuance History: {record.issuance_history}, URL: {record.url}, Date: {record.today}")
#
