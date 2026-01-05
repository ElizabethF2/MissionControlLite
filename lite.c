#include <stdio.h>
#include <stdlib.h> 
#include <unistd.h>

#include <curl/curl.h>

#define ERROR_TOO_FEW_ARGS 1

#if DEBUG
#include <ctype.h>
#endif

int char_count;

size_t write_callback(char* ptr, size_t size, size_t nmemb, void* unused)
{
  for (int i=0; i < nmemb; ++i)
  {
    char c = ptr[i];
    if (c != ' ' && c != '\n' && c != '\t' && c != '\r' && c != '\0')
    {
      ++char_count;
#if DEBUG
      if (isprint(c) && !isspace(c))
      {
        printf("Received: %c\n", c);
      }
      else
      {
        printf("Received: (char %d)\n", c);
      }
#endif
    }
  }

  return nmemb;
}

int main(int argc, char *argv[])
{
  if (argc < 7)
  {
#if DEBUG
    printf("usage: %s [delay] [timeout] [certificate] [url] [server script] [network fixer script]\n", argv[0]);
#endif
    return ERROR_TOO_FEW_ARGS;
  }

  unsigned long delay = strtoul(argv[1], NULL, 0);
  unsigned long timeout = strtoul(argv[2], NULL, 0);

#if DEBUG
    printf("delay = %lu\n", delay);
    printf("timeout = %lu\n", timeout);
#endif

  while (1)
  {
#if DEBUG
    printf("Sleeping\n");
#endif
    sleep(delay);

#if DEBUG
    printf("Checking wake inbox\n");
#endif

    CURL* curl = curl_easy_init();

#if USE_SMALL_CURL_BUFFER
    curl_easy_setopt(curl, CURLOPT_BUFFERSIZE, 1024L);
#endif

    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_CAINFO, argv[3]);
    curl_easy_setopt(curl, CURLOPT_URL, argv[4]);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout);

    char_count = 0;
    CURLcode res = curl_easy_perform(curl);

#if DEBUG
    printf("res = %s\n", curl_easy_strerror(res));
    printf("char_count = %d\n", char_count);
#endif

    if (res == CURLE_OK)
    {
      if (char_count > 2)
      {
#if DEBUG
        printf("Starting server\n");
#endif

        FILE* proc = popen(argv[5], "w");
        pclose(proc);

#if DEBUG
        printf("Server finished\n");
#endif
      }
    }
    else
    {
#if DEBUG
      printf("Starting network repair tool\n");
#endif

      FILE* proc = popen(argv[6], "w");
      pclose(proc);

#if DEBUG
      printf("Network repair tool finished\n");
#endif
    }

    curl_easy_cleanup(curl);
  }

  return 0;
}
