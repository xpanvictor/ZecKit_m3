
# Use official Zebra image from Zcash Foundation
FROM zfnd/zebra:latest

# Add entrypoint if needed
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /var/zebra
EXPOSE 8232 8233
ENTRYPOINT ["/entrypoint.sh"]
CMD ["zebrad", "start"]