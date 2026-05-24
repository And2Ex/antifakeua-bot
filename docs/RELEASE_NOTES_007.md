# AntiFakeUA Bot — Release 007

## Payment button cleanup

- Removed the extra **«Обрати інший пакет»** button from the LiqPay payment screen.
- Changed the main menu payment callback from `buy:menu` to `buy_menu` so it cannot be accidentally processed as a package id.
- Added backward compatibility: old inline messages with `buy:menu` still open the package list instead of showing **«Пакет не знайдено»**.

## Why

The previous callback `buy:menu` used the same prefix as package callbacks (`buy:<package_id>`), so aiogram could route it into the generic package handler.
