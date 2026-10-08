import kagglehub

# function is failing to download, with an error Resource not found.
def extract_customer_churn_kaggle_data(dataset_name, download_path):

    path = kagglehub.dataset_download(dataset_name, download_path)
    return path

if __name__ == "__main__":
    dataset_name = "muhammadshahidazeem/customer-churn-dataset"
    download_path = "data/raw"

    path = extract_customer_churn_kaggle_data(dataset_name, download_path)
    print(f"Dataset downloaded to: {path}")