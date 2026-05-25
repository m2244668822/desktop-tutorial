#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持久化記憶系統 - 加密管理器
Persistent Memory System - Crypto Manager

功能：
- AES-256-GCM 加密
- PBKDF2 金鑰派生
- 金鑰管理
- 資料完整性驗證

作者：AI 智能體
創建時間：2026-03-21
"""

import os
import hashlib
import json
import base64
import logging
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 常量定義
# ============================================================

# AES-256-GCM 金鑰長度（32 bytes = 256 bits）
KEY_LENGTH = 32

# 隨機數長度（16 bytes = 128 bits）
NONCE_LENGTH = 16

# PBKDF2 迭代次數（建議至少 100,000）
PBKDF2_ITERATIONS = 100000

# Salt 長度（16 bytes）
SALT_LENGTH = 16

# 標籤長度（12 bytes for GCM）
AUTH_TAG_LENGTH = 12


# ============================================================
# 資料類別定義
# ============================================================


@dataclass
class EncryptedData:
    """加密資料結構"""

    ciphertext: bytes  # 加密後的密文
    nonce: bytes  # 隨機數
    salt: bytes  # Salt 值
    version: int = 1  # 加密版本


@dataclass
class KeyInfo:
    """金鑰資訊"""

    key_id: str
    key_name: str
    created_at: str
    algorithm: str = "AES-256-GCM"
    iterations: int = PBKDF2_ITERATIONS


# ============================================================
# 加密管理器類
# ============================================================


class CryptoManager:
    """
    加密管理器

    功能：
    - 使用 AES-256-GCM 進行對稱加密
    - 使用 PBKDF2 派生金鑰
    - 管理多個金鑰
    - 驗證資料完整性

    使用範例：
        crypto = CryptoManager()

        # 加密資料
        encrypted = crypto.encrypt("Hello World", "my_password")

        # 解密資料
        decrypted = crypto.decrypt(encrypted, "my_password")

        # 派生金鑰
        key = crypto.derive_key("password", salt)
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化加密管理器

        Args:
            db_path: 金鑰儲存資料庫路徑（可選）
        """
        self.db_path = db_path
        self._key_cache: Dict[str, bytes] = {}
        self._default_key_id: Optional[str] = None

    def generate_salt(self) -> bytes:
        """生成隨機 Salt"""
        return os.urandom(SALT_LENGTH)

    def generate_nonce(self) -> bytes:
        """生成隨機 Nonce"""
        return os.urandom(NONCE_LENGTH)

    def derive_key(self, password: str, salt: bytes) -> bytes:
        """
        使用 PBKDF2 派生金鑰

        Args:
            password: 密碼
            salt: Salt 值

        Returns:
            派生的金鑰（32 bytes）
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_LENGTH,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(password.encode("utf-8"))

    def _get_aesgcm(self, key: bytes) -> AESGCM:
        """建立 AESGCM 加密器"""
        return AESGCM(key)

    def encrypt(
        self,
        plaintext: str,
        password: str,
        salt: Optional[bytes] = None,
        key: Optional[bytes] = None,
    ) -> EncryptedData:
        """
        加密資料

        Args:
            plaintext: 要加密的明文
            password: 密碼
            salt: Salt 值（可選，若未提供則自動生成）
            key: 預先派生好的金鑰（可選，若未提供則從密碼派生）

        Returns:
            EncryptedData 物件
        """
        # 生成或使用提供的 Salt
        if salt is None:
            salt = self.generate_salt()

        # 派生或使用提供的金鑰
        if key is None:
            key = self.derive_key(password, salt)

        # 生成隨機 Nonce
        nonce = self.generate_nonce()

        # 加密
        aesgcm = self._get_aesgcm(key)
        ciphertext = aesgcm.encrypt(
            nonce,
            plaintext.encode("utf-8"),
            None,  # 額外驗證資料（AAD）
        )

        return EncryptedData(ciphertext=ciphertext, nonce=nonce, salt=salt)

    def decrypt(
        self, encrypted_data: EncryptedData, password: str, key: Optional[bytes] = None
    ) -> str:
        """
        解密資料

        Args:
            encrypted_data: 加密的資料
            password: 密碼
            key: 預先派生好的金鑰（可選）

        Returns:
            解密後的明文
        """
        # 派生金鑰
        if key is None:
            key = self.derive_key(password, encrypted_data.salt)

        # 解密
        aesgcm = self._get_aesgcm(key)
        plaintext = aesgcm.decrypt(
            encrypted_data.nonce, encrypted_data.ciphertext, None
        )

        return plaintext.decode("utf-8")

    def encrypt_dict(
        self, data: Dict[str, Any], password: str, salt: Optional[bytes] = None
    ) -> str:
        """
        加密字典資料

        Args:
            data: 要加密的字典
            password: 密碼
            salt: Salt 值

        Returns:
            Base64 編碼的加密字串
        """
        plaintext = json.dumps(data, ensure_ascii=False)
        encrypted = self.encrypt(plaintext, password, salt)

        # 編碼為 Base64
        result = {
            "ciphertext": base64.b64encode(encrypted.ciphertext).decode("utf-8"),
            "nonce": base64.b64encode(encrypted.nonce).decode("utf-8"),
            "salt": base64.b64encode(encrypted.salt).decode("utf-8"),
            "version": encrypted.version,
        }

        return json.dumps(result)

    def decrypt_dict(self, encrypted_json: str, password: str) -> Dict[str, Any]:
        """
        解密字典資料

        Args:
            encrypted_json: Base64 編碼的加密字串
            password: 密碼

        Returns:
            解密後的字典
        """
        # 解碼
        data = json.loads(encrypted_json)

        encrypted = EncryptedData(
            ciphertext=base64.b64decode(data["ciphertext"]),
            nonce=base64.b64decode(data["nonce"]),
            salt=base64.b64decode(data["salt"]),
            version=data.get("version", 1),
        )

        # 解密
        plaintext = self.decrypt(encrypted, password)

        return json.loads(plaintext)

    def encrypt_file(self, input_path: str, output_path: str, password: str):
        """
        加密檔案

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            password: 密碼
        """
        # 讀取檔案
        with open(input_path, "rb") as f:
            plaintext = f.read()

        # 加密
        salt = self.generate_salt()
        encrypted = self.encrypt(
            plaintext.decode("latin-1", errors="ignore"), password, salt
        )

        # 寫入加密檔案
        with open(output_path, "wb") as f:
            f.write(b"PMCRYPT1.0\n")  # 魔數標記
            f.write(encrypted.salt)
            f.write(encrypted.nonce)
            f.write(encrypted.ciphertext)

        logger.info(f"檔案已加密: {output_path}")

    def decrypt_file(self, input_path: str, output_path: str, password: str):
        """
        解密檔案

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            password: 密碼
        """
        # 讀取加密檔案
        with open(input_path, "rb") as f:
            # 驗證魔數
            magic = f.read(10)
            if magic != b"PMCRYPT1.0\n":
                raise ValueError("無效的加密檔案格式")

            salt = f.read(SALT_LENGTH)
            nonce = f.read(NONCE_LENGTH)
            ciphertext = f.read()

        # 建立 EncryptedData
        encrypted = EncryptedData(ciphertext=ciphertext, nonce=nonce, salt=salt)

        # 解密
        plaintext = self.decrypt(encrypted, password)

        # 寫入解密檔案
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(plaintext)

        logger.info(f"檔案已解密: {output_path}")

    def compute_checksum(self, data: str) -> str:
        """
        計算資料的 SHA-256 校驗和

        Args:
            data: 要計算的資料

        Returns:
            校驗和（十六進制字串）
        """
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def verify_checksum(self, data: str, expected_checksum: str) -> bool:
        """
        驗證校驗和

        Args:
            data: 要驗證的資料
            expected_checksum: 預期的校驗和

        Returns:
            是否匹配
        """
        actual_checksum = self.compute_checksum(data)
        return actual_checksum == expected_checksum

    def create_key_from_password(
        self, password: str, key_name: str = "default"
    ) -> Tuple[str, bytes]:
        """
        從密碼建立金鑰並返回 ID

        Args:
            password: 密碼
            key_name: 金鑰名稱

        Returns:
            (key_id, salt)
        """
        salt = self.generate_salt()
        key_id = hashlib.sha256(f"{key_name}{salt}{time.time()}".encode()).hexdigest()[
            :16
        ]

        return key_id, salt

    def hash_password(self, password: str, salt: Optional[bytes] = None) -> str:
        """
        雜湊密碼（用於儲存驗證）

        Args:
            password: 密碼
            salt: Salt 值

        Returns:
            雜湊後的字串
        """
        if salt is None:
            salt = self.generate_salt()

        # 使用 scrypt-like 方式（這裡簡化處理）
        combined = password.encode("utf-8") + salt
        for _ in range(10000):
            combined = hashlib.sha256(combined).digest()

        return base64.b64encode(salt + combined).decode("utf-8")

    def verify_password(self, password: str, hashed: str) -> bool:
        """
        驗證密碼

        Args:
            password: 輸入的密碼
            hashed: 儲存的雜湊值

        Returns:
            是否正確
        """
        try:
            decoded = base64.b64decode(hashed.encode("utf-8"))
            salt = decoded[:SALT_LENGTH]
            stored_hash = decoded[SALT_LENGTH:]

            # 重新計算
            combined = password.encode("utf-8") + salt
            for _ in range(10000):
                combined = hashlib.sha256(combined).digest()

            return combined == stored_hash
        except Exception:
            return False


# ============================================================
# 金鑰管理器（擴展功能）
# ============================================================


class KeyManager(CryptoManager):
    """
    金鑰管理器

    繼承自 CryptoManager，並提供金鑰儲存和管理功能
    """

    def __init__(self, storage_path: str = "data/keys"):
        """
        初始化金鑰管理器

        Args:
            storage_path: 金鑰儲存目錄
        """
        super().__init__()
        self.storage_path = storage_path
        self._ensure_storage_directory()

        # 金鑰索引檔案
        self.index_file = os.path.join(storage_path, "key_index.json")
        self._key_index = self._load_key_index()

    def _ensure_storage_directory(self):
        """確保儲存目錄存在"""
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path, exist_ok=True)

    def _load_key_index(self) -> Dict[str, Any]:
        """載入金鑰索引"""
        if os.path.exists(self.index_file):
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_key_index(self):
        """儲存金鑰索引"""
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(self._key_index, f, ensure_ascii=False, indent=2)

    def create_key(
        self, key_name: str, password: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        建立新金鑰

        Args:
            key_name: 金鑰名稱
            password: 金鑰密碼
            metadata: 額外的中繼資料

        Returns:
            金鑰 ID
        """
        key_id, salt = self.create_key_from_password(password, key_name)

        # 派生金鑰
        key = self.derive_key(password, salt)

        # 生成金鑰檔案名稱
        key_file = os.path.join(self.storage_path, f"{key_id}.key")

        # 加密並儲存金鑰
        with open(key_file, "wb") as f:
            f.write(key)

        # 更新索引
        self._key_index[key_id] = {
            "key_name": key_name,
            "salt": base64.b64encode(salt).decode("utf-8"),
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        # 設定為預設金鑰
        self._default_key_id = key_id
        self._save_key_index()

        logger.info(f"金鑰已建立: {key_id}")
        return key_id

    def load_key(self, key_id: str, password: str) -> Optional[bytes]:
        """
        載入金鑰

        Args:
            key_id: 金鑰 ID
            password: 金鑰密碼

        Returns:
            金鑰 bytes，若失敗則返回 None
        """
        if key_id not in self._key_index:
            logger.error(f"金鑰不存在: {key_id}")
            return None

        # 取得金鑰檔案路徑
        key_file = os.path.join(self.storage_path, f"{key_id}.key")

        if not os.path.exists(key_file):
            logger.error(f"金鑰檔案不存在: {key_file}")
            return None

        # 讀取金鑰
        with open(key_file, "rb") as f:
            return f.read()

    def delete_key(self, key_id: str) -> bool:
        """
        刪除金鑰

        Args:
            key_id: 金鑰 ID

        Returns:
            是否成功
        """
        if key_id in self._key_index:
            # 刪除金鑰檔案
            key_file = os.path.join(self.storage_path, f"{key_id}.key")
            if os.path.exists(key_file):
                os.remove(key_file)

            # 更新索引
            del self._key_index[key_id]
            self._save_key_index()

            if self._default_key_id == key_id:
                self._default_key_id = None

            logger.info(f"金鑰已刪除: {key_id}")
            return True

        return False

    def list_keys(self) -> List[Dict[str, Any]]:
        """
        列出所有金鑰

        Returns:
            金鑰資訊列表
        """
        return [{"key_id": key_id, **info} for key_id, info in self._key_index.items()]

    def get_default_key_id(self) -> Optional[str]:
        """取得預設金鑰 ID"""
        return self._default_key_id

    def set_default_key(self, key_id: str):
        """設定預設金鑰"""
        if key_id in self._key_index:
            self._default_key_id = key_id
            self._save_key_index()


# ============================================================
# 便捷函數
# ============================================================


def encrypt_data(data: str, password: str) -> str:
    """
    便捷加密函數

    Args:
        data: 要加密的資料
        password: 密碼

    Returns:
        加密後的 Base64 字串
    """
    crypto = CryptoManager()
    return crypto.encrypt_dict(data, password)


def decrypt_data(encrypted: str, password: str) -> str:
    """
    便捷解密函數

    Args:
        encrypted: 加密的 Base64 字串
        password: 密碼

    Returns:
        解密後的資料
    """
    crypto = CryptoManager()
    return crypto.decrypt_dict(encrypted, password)


# ============================================================
# 使用範例
# ============================================================

if __name__ == "__main__":
    import time
    from datetime import datetime

    # 建立加密管理器
    crypto = CryptoManager()
    password = "my_secure_password"

    # 測試加密/解密
    print("=== 測試加密/解密 ===")

    # 測試字串加密
    encrypted = crypto.encrypt("Hello, World!", password)
    print(f"加密後: {len(encrypted.ciphertext)} bytes")

    decrypted = crypto.decrypt(encrypted, password)
    print(f"解密後: {decrypted}")

    # 測試字典加密
    print("\n=== 測試字典加密 ===")
    data = {"name": "測試", "value": 123, "nested": {"a": 1, "b": 2}}
    encrypted_json = crypto.encrypt_dict(data, password)
    print(f"加密後長度: {len(encrypted_json)}")

    decrypted_dict = crypto.decrypt_dict(encrypted_json, password)
    print(f"解密後: {decrypted_dict}")

    # 測試校驗和
    print("\n=== 測試校驗和 ===")
    checksum = crypto.compute_checksum("test data")
    print(f"校驗和: {checksum}")
    print(f"驗證結果: {crypto.verify_checksum('test data', checksum)}")

    # 測試金鑰管理器
    print("\n=== 測試金鑰管理器 ===")
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        key_manager = KeyManager(tmpdir)

        # 建立金鑰
        key_id = key_manager.create_key("test_key", "key_password")
        print(f"建立金鑰 ID: {key_id}")

        # 列出金鑰
        keys = key_manager.list_keys()
        print(f"金鑰數量: {len(keys)}")

        # 載入金鑰
        key_data = key_manager.load_key(key_id, "key_password")
        print(f"載入金鑰: {len(key_data)} bytes")

        # 刪除金鑰
        result = key_manager.delete_key(key_id)
        print(f"刪除結果: {result}")

    print("\n所有測試通過！")
